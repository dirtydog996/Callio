from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from pipecat.frames.frames import Frame, InterruptionFrame, TextFrame, TranscriptionFrame, TTSTextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from callio.config.settings import Settings, get_settings
from callio.voice.context_updater import refresh_system_prompt

if TYPE_CHECKING:
    from callio.orchestrator import Orchestrator
    from pipecat.processors.aggregators.llm_context import LLMContext

logger = logging.getLogger(__name__)

_REFRESH_INTERVAL_SEC = 3.0


class SessionHook(FrameProcessor):
    """Transcript capture + dynamic progress/memory injection + barge-in client notification."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        session_id: str,
        context: LLMContext,
        settings: Settings | None = None,
        memory_hub=None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._orchestrator = orchestrator
        self._session_id = session_id
        self._context = context
        self._settings = settings or get_settings()
        self._memory_hub = memory_hub
        self._last_refresh: float = 0.0
        # Tracks node_ids whose results have already been reported to the user
        # so we only surface each completion once per voice session.
        self._announced_completions: set[str] = set()

    def _collect_new_completions(self) -> list[dict]:
        """Return completed tasks with results not yet announced in this session."""
        fresh = self._orchestrator.database.list_completed_with_results(self._session_id)
        return [t for t in fresh if str(t["node_id"]) not in self._announced_completions]

    def _mark_announced(self, tasks: list[dict]) -> None:
        for t in tasks:
            self._announced_completions.add(str(t["node_id"]))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        try:
            if isinstance(frame, TranscriptionFrame) and frame.text:
                self._orchestrator.transcripts.append(self._session_id, "user", frame.text)
                now = time.monotonic()
                # Check for new task completions; force a refresh if any are found
                # so the proactive note is visible to the LLM for this turn.
                new_completions = self._collect_new_completions()
                force_refresh = bool(new_completions)
                if force_refresh or now - self._last_refresh >= _REFRESH_INTERVAL_SEC:
                    self._last_refresh = now
                    await refresh_system_prompt(
                        self._context,
                        self._orchestrator,
                        self._session_id,
                        self._settings,
                        memory_hub=self._memory_hub,
                        announced=self._announced_completions,
                    )
                    # Mark completions as announced after the prompt has been
                    # updated so they won't repeat on subsequent turns.
                    if new_completions:
                        self._mark_announced(new_completions)
                        logger.info(
                            "Proactive notification injected for %d task(s) in session %s",
                            len(new_completions),
                            self._session_id,
                        )
                await self._orchestrator.transcripts.maybe_schedule_summary(self._session_id)
            elif isinstance(frame, (TextFrame, TTSTextFrame)) and frame.text:
                self._orchestrator.transcripts.append(self._session_id, "assistant", frame.text)
            elif isinstance(frame, InterruptionFrame):
                logger.debug("Barge-in: user interrupted assistant")
        except Exception as exc:
            logger.warning("Session hook failed: %s", exc)
        await self.push_frame(frame, direction)
