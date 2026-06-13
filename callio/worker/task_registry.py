from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio.subprocess as subprocess

logger = logging.getLogger(__name__)


class TaskRegistry:
    """跟踪 RUNNING 子进程，支持取消。"""

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._cancelled: set[str] = set()

    def track(self, node_id: str, process: asyncio.subprocess.Process) -> None:
        self._processes[node_id] = process

    def is_cancelled(self, node_id: str) -> bool:
        return node_id in self._cancelled

    async def cancel(self, node_id: str) -> bool:
        self._cancelled.add(node_id)
        process = self._processes.get(node_id)
        if process is None or process.returncode is not None:
            return True
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        logger.info("Cancelled task %s", node_id)
        return True

    def clear(self, node_id: str) -> None:
        self._processes.pop(node_id, None)
        self._cancelled.discard(node_id)


registry = TaskRegistry()
