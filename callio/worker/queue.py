from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

from callio.core.database import Database

logger = logging.getLogger(__name__)

RunHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class TaskQueue:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._pump_lock = asyncio.Lock()

    def enqueue(self, payload: dict[str, Any]) -> int:
        return self.database.enqueue_task(json.dumps(payload, ensure_ascii=False))

    def pending_count(self) -> int:
        return self.database.count_queued_tasks("PENDING")

    def reset_stale(self) -> int:
        return self.database.reset_claimed_tasks()

    async def pump(self, handler: RunHandler, *, global_limit: int) -> int:
        started = 0
        async with self._pump_lock:
            while self.database.count_running_tasks_global() < global_limit:
                item = self.database.claim_next_task()
                if item is None:
                    break
                queue_id, payload = item
                asyncio.create_task(self._run_claimed(queue_id, payload, handler))
                started += 1
        return started

    async def _run_claimed(self, queue_id: int, payload: dict[str, Any], handler: RunHandler) -> None:
        node_id = str(payload.get("node_id", ""))
        try:
            await handler(payload)
            self.database.complete_task(queue_id, "DONE")
        except Exception as exc:
            logger.exception("Queued task failed: %s", node_id)
            self.database.complete_task(queue_id, "FAILED")
            if node_id:
                self.database.update_spec_status(node_id, "FAILED", str(exc), phase="FAILED")
