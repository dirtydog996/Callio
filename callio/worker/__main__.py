"""Standalone worker process for SQLite task queue."""

from __future__ import annotations

import asyncio
import logging

from callio.config.settings import get_settings
from callio.core.database import Database
from callio.core.memory import MemoryHub
from callio.worker.tasks import TaskDispatcher

logger = logging.getLogger(__name__)


class _NoopStatusManager:
    async def broadcast_status(self, message: dict[str, object]) -> None:
        logger.info("task event: %s", message.get("event"))


async def _run() -> None:
    settings = get_settings()
    database = Database(settings)
    database.initialize()
    memory_hub = MemoryHub(database, settings)
    dispatcher = TaskDispatcher(database, memory_hub, _NoopStatusManager(), settings)

    resumed = await dispatcher.resume_pending()
    if resumed:
        logger.info("Resumed %d queued tasks", resumed)

    while True:
        pending = dispatcher.queue.pending_count()
        if pending:
            await dispatcher.resume_pending()
        await asyncio.sleep(2)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
