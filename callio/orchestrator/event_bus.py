from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from callio.core.database import Database
from callio.core.session_events import SessionEventStore

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self, database: Database, events: SessionEventStore, broadcast: BroadcastFn) -> None:
        self.database = database
        self.events = events
        self.broadcast = broadcast

    async def emit(self, session_id: str, event: str, payload: dict[str, Any]) -> None:
        self.events.append(session_id, event, payload)
        message = {"event": event, "session_id": session_id, **payload}
        try:
            await self.broadcast(message)
        except Exception:
            logger.exception("Event broadcast failed for %s", event)
