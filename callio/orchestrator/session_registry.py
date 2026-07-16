from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from callio.core.database import Database
from callio.orchestrator.event_bus import EventBus


@dataclass
class SessionContext:
    session_id: str
    title: str
    resumed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionRegistry:
    def __init__(self, database: Database, event_bus: EventBus) -> None:
        self.database = database
        self.event_bus = event_bus
        self._active: dict[int, SessionContext] = {}

    def open(
        self,
        connection_id: int,
        *,
        title: str | None = None,
        resume_session_id: str | None = None,
    ) -> SessionContext:
        if resume_session_id:
            existing = self.database.get_session(resume_session_id)
            if existing:
                label = str(existing.get("title") or title or f"voice-session-{resume_session_id[:8]}")
                self.database.update_session(resume_session_id, clear_ended_at=True)
                ctx = SessionContext(session_id=resume_session_id, title=label, resumed=True)
                self._active[connection_id] = ctx
                return ctx

        session_id = str(uuid.uuid4())
        label = title or f"voice-session-{session_id[:8]}"
        self.database.create_session(session_id, label)
        ctx = SessionContext(session_id=session_id, title=label)
        self._active[connection_id] = ctx
        return ctx

    def get(self, connection_id: int) -> SessionContext | None:
        return self._active.get(connection_id)

    async def finalize(self, connection_id: int, *, transcript: str = "") -> SessionContext | None:
        ctx = self._active.pop(connection_id, None)
        if not ctx:
            return None
        ended = datetime.now(timezone.utc).isoformat()
        if transcript:
            self.database.update_session(ctx.session_id, transcript=transcript, ended_at=ended)
        else:
            self.database.update_session(ctx.session_id, ended_at=ended)
        await self.event_bus.emit(
            ctx.session_id,
            "SESSION_ENDED",
            {"title": ctx.title, "ended_at": ended, "resumed": ctx.resumed},
        )
        return ctx
