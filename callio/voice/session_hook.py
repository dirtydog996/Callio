from __future__ import annotations

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

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        try:
            if isinstance(frame, TranscriptionFrame) and frame.text:
                self._orchestrator.transcripts.append(self._session_id, "user", frame.text)
                now = time.monotonic()
                if now - self._last_refresh >= _REFRESH_INTERVAL_SEC:
                    self._last_refresh = now
                    await refresh_system_prompt(
                        self._context,
                        self._orchestrator,
                        self._session_id,
                        self._settings,
                        memory_hub=self._memory_hub,
                    )
                await self._orchestrator.transcripts.maybe_schedule_summary(self._session_id)
            elif isinstance(frame, (TextFrame, TTSTextFrame)) and frame.text:
                self._orchestrator.transcripts.append(self._session_id, "assistant", frame.text)
            elif isinstance(frame, InterruptionFrame):
                logger.debug("Barge-in: user interrupted assistant")
        except Exception as exc:
            logger.warning("Session hook failed: %s", exc)
        await self.push_frame(frame, direction)
