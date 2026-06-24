from __future__ import annotations

import asyncio
import logging
from typing import Any

from callio.config.settings import Settings, get_settings
from callio.core.database import Database
from callio.core.memory import MemoryHub
from callio.core.task_log import TaskLog
from callio.worker.cancel import TaskCancelService
from callio.worker.kinds import TaskKind
from callio.worker.prompt_builder import build_execute_prompt
from callio.worker.queue import TaskQueue
from callio.worker.runner import WorkerRunner
from callio.worker.runners.analyze_runner import AnalyzeRunner
from callio.worker.runners.summarize_runner import SummarizeRunner
from callio.worker.task_registry import registry

logger = logging.getLogger(__name__)


class TaskDispatcher:
    def __init__(
        self,
        database: Database,
        memory_hub: MemoryHub,
        status_manager: Any,
        settings: Settings | None = None,
    ) -> None:
        self.database = database
        self.memory_hub = memory_hub
        self.status_manager = status_manager
        self.settings = settings or get_settings()
        self.runner = WorkerRunner(database, self.settings)
        self.summarize_runner = SummarizeRunner(database, memory_hub, self.settings)
        self.analyze_runner = AnalyzeRunner(database, self.settings)
        self.task_log = TaskLog(database)
        self.queue = TaskQueue(database)
        self.cancel_service = TaskCancelService(database)
        self.backend_name = "sqlite-queue"

    async def dispatch(self, payload: dict[str, Any]) -> None:
        self.queue.enqueue(payload)
        await self._pump()

    async def resume_pending(self) -> int:
        reset = self.queue.reset_stale()
        if reset:
            logger.info("Reset %d stale queued tasks", reset)
        return await self._pump()

    async def cancel_running(self, node_id: str) -> dict[str, object]:
        result = await self.cancel_service.cancel_running(node_id)
        if result.get("cancelled"):
            await self.status_manager.broadcast_status({
                "event": "TASK_COMPLETED",
                "node_id": node_id,
                "status": "CANCELLED",
                "progress": 100,
            })
        return result

    async def _pump(self) -> int:
        return await self.queue.pump(self._run, global_limit=self.settings.global_max_parallel)

    async def _run(self, payload: dict[str, Any]) -> None:
        node_id = str(payload.get("node_id", ""))
        timeout = self.settings.task_timeout_sec
        try:
            if timeout > 0:
                await asyncio.wait_for(self._execute(payload), timeout=timeout)
            else:
                await self._execute(payload)
        except asyncio.TimeoutError:
            await registry.cancel(node_id)
            registry.clear(node_id)
            error = f"Task timed out (>{timeout}s)"
            self.database.update_spec_status(node_id, "FAILED", error, phase="FAILED")
            await self.status_manager.broadcast_status({
                "event": "TASK_COMPLETED",
                "node_id": node_id,
                "session_id": payload.get("session_id"),
                "status": "FAILED",
                "error": error,
                "progress": 100,
            })
        except asyncio.CancelledError:
            registry.clear(node_id)
            raise
        finally:
            registry.clear(node_id)
            await self._pump()

    async def _execute(self, payload: dict[str, Any]) -> None:
        session_id = payload.get("session_id")
        description = str(payload.get("description", ""))
        node_id = str(payload.get("node_id"))
        kind = str(payload.get("kind", TaskKind.EXECUTE.value)).upper()

        if registry.is_cancelled(node_id):
            return

        if session_id:
            self.memory_hub.append_session_token(session_id, description)

        async def progress_callback(message: dict[str, object]) -> None:
            if session_id and "session_id" not in message:
                message = {**message, "session_id": session_id}
            await self.status_manager.broadcast_status(message)

        if kind == TaskKind.SUMMARIZE.value:
            await self.summarize_runner.run(node_id, str(session_id), description, progress_callback)
            return

        if kind == TaskKind.ANALYZE.value:
            await self.analyze_runner.run(node_id, str(session_id), description, progress_callback)
            return

        run_id = self.task_log.start_run(node_id, str(session_id or ""), kind)
        self.database.update_spec_status(node_id, "RUNNING", phase="RUNNING")

        async def execute_progress(message: dict[str, object]) -> None:
            if registry.is_cancelled(node_id):
                return
            if "progress" in message:
                self.task_log.append_stdout(
                    run_id,
                    f"progress={message.get('progress')}",
                    progress_pct=int(message.get("progress", 0)) if message.get("progress") is not None else None,
                )
            await progress_callback(message)

        task_text = description
        if kind == TaskKind.EXECUTE.value and session_id:
            task_text = build_execute_prompt(self.database, node_id, str(session_id))

        try:
            await self.runner.execute(node_id, task_text, execute_progress)
            if not registry.is_cancelled(node_id):
                self.task_log.finish_run(run_id, "SUCCESS")
        except Exception as exc:
            self.task_log.append_stdout(run_id, str(exc))
            self.task_log.finish_run(run_id, "FAILED")
            raise
