from __future__ import annotations

import asyncio
from typing import Any

from callio.config.settings import Settings, get_settings
from callio.core.database import Database
from callio.core.memory import MemoryHub
from callio.worker.runner import WorkerRunner


class TaskDispatcher:
    def __init__(self, database: Database, memory_hub: MemoryHub, status_manager: Any, settings: Settings | None = None) -> None:
        self.database = database
        self.memory_hub = memory_hub
        self.status_manager = status_manager
        self.settings = settings or get_settings()
        self.runner = WorkerRunner(database, self.settings)
        self.backend_name = "asyncio"

    async def dispatch(self, payload: dict[str, Any]) -> None:
        asyncio.create_task(self._run(payload))

    async def _run(self, payload: dict[str, Any]) -> None:
        session_id = payload.get("session_id")
        description = str(payload.get("description", ""))
        if session_id:
            self.memory_hub.append_session_token(session_id, description)
        await self.runner.execute(payload["node_id"], description, self.status_manager.broadcast_status)
