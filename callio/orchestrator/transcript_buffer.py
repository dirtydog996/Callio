from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from callio.config.settings import Settings
from callio.core.database import Database
from callio.orchestrator.event_bus import EventBus

if TYPE_CHECKING:
    from callio.orchestrator.task_coordinator import TaskCoordinator


class TranscriptBuffer:
    def __init__(
        self,
        database: Database,
        event_bus: EventBus,
        settings: Settings,
        coordinator: TaskCoordinator | None = None,
    ) -> None:
        self.database = database
        self.event_bus = event_bus
        self.settings = settings
        self.coordinator = coordinator
        self._lines: dict[str, list[str]] = {}
        self._last_summary_at: dict[str, float] = {}
        self._turn_counts: dict[str, int] = {}

    def append(self, session_id: str, role: str, text: str) -> None:
        line = text.strip()
        if not line:
            return
        bucket = self._lines.setdefault(session_id, [])
        bucket.append(f"{role}: {line}")
        if role == "user":
            self._turn_counts[session_id] = self._turn_counts.get(session_id, 0) + 1

    def get_transcript(self, session_id: str) -> str:
        return "\n".join(self._lines.get(session_id, []))

    def hydrate(self, session_id: str, transcript: str) -> None:
        lines: list[str] = []
        turns = 0
        for line in transcript.splitlines():
            text = line.strip()
            if not text:
                continue
            lines.append(text)
            if text.startswith("user:"):
                turns += 1
        if lines:
            self._lines[session_id] = lines
            self._turn_counts[session_id] = turns

    async def flush(self, session_id: str) -> str:
        transcript = self.get_transcript(session_id)
        if transcript:
            self.database.update_session(session_id, transcript=transcript)
            await self.event_bus.emit(session_id, "TRANSCRIPT_FLUSH", {"length": len(transcript)})
        return transcript

    async def maybe_schedule_summary(self, session_id: str) -> None:
        if self.coordinator is None:
            return
        now = time.monotonic()
        last = self._last_summary_at.get(session_id, 0.0)
        turns = self._turn_counts.get(session_id, 0)
        if now - last < self.settings.summarize_debounce_sec and turns % 5 != 0:
            return
        transcript = self.get_transcript(session_id)
        if len(transcript) < 40:
            return
        self._last_summary_at[session_id] = now
        asyncio.create_task(
            self.coordinator.dispatch_background_summary(session_id, transcript)
        )
