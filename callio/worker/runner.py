from __future__ import annotations

import asyncio
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from callio.config.settings import Settings, get_settings
from callio.core.database import Database
from callio.worker.agent_resolver import AgentResolver
from callio.worker.sandbox import SandboxManager
from callio.worker.task_registry import registry

ProgressCallback = Callable[[dict[str, object]], Awaitable[None]]
_PROGRESS_RE = re.compile(r"(?P<passed>\d+)\s+passed(?:\s+tests?)?.*?(?P<total>\d+)\s+total", re.IGNORECASE)


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class GitCheckpointManager:
    def __init__(self, workspace: Path, settings: Settings | None = None) -> None:
        self.workspace = workspace
        self.settings = settings or get_settings()
        self.base_dir = Path(tempfile.gettempdir()) / "callio_checkpoints"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, node_id: str, attempt: int) -> Path | None:
        if not (self.workspace / ".git").exists():
            return None
        checkpoint = self.base_dir / f"{node_id}-attempt-{attempt}.diff"
        process = await asyncio.create_subprocess_exec(
            "git", "diff", cwd=self.workspace,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        checkpoint.write_bytes(stdout)
        return checkpoint

    async def rollback(self) -> None:
        if not self.settings.enable_git_resets:
            return
        process = await asyncio.create_subprocess_exec(
            "git", "reset", "--hard", cwd=self.workspace,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()


class WorkerRunner:
    def __init__(self, database: Database, settings: Settings | None = None) -> None:
        self.database = database
        self.settings = settings or get_settings()
        self.sandbox_manager = SandboxManager(self.settings)
        self.agent_resolver = AgentResolver(self.settings)

    async def execute(self, node_id: str, description: str, progress_callback: ProgressCallback) -> None:
        resolved = self.agent_resolver.resolve(description)
        if resolved is None:
            error = self.agent_resolver.missing_message()
            self.database.update_spec_status(node_id, "FAILED", error, phase="FAILED")
            await progress_callback({
                "event": "TASK_COMPLETED", "node_id": node_id,
                "status": "FAILED", "error": error, "progress": 100,
            })
            return

        session = self.sandbox_manager.prepare_workspace(node_id)
        checkpoints = GitCheckpointManager(session.workspace, self.settings)
        self.database.update_spec_status(node_id, "RUNNING", phase="RUNNING")
        await progress_callback({
            "event": "TASK_RUNNING", "node_id": node_id,
            "status": "RUNNING", "agent": resolved.backend, "progress": 0,
        })

        last_error = ""
        max_attempts = self.settings.execute_max_retries
        for attempt in range(1, max_attempts + 1):
            if registry.is_cancelled(node_id):
                self.database.update_spec_status(node_id, "CANCELLED", "用户取消", phase="CANCELLED")
                await progress_callback({
                    "event": "TASK_COMPLETED", "node_id": node_id,
                    "status": "CANCELLED", "progress": 100,
                })
                return
            await checkpoints.save(node_id, attempt)
            result = await self._run_command(session.workspace, resolved.argv, progress_callback, node_id)
            if registry.is_cancelled(node_id):
                self.database.update_spec_status(node_id, "CANCELLED", "用户取消", phase="CANCELLED")
                await progress_callback({
                    "event": "TASK_COMPLETED", "node_id": node_id,
                    "status": "CANCELLED", "progress": 100,
                })
                return
            if result.returncode == 0:
                self.database.update_spec_status(node_id, "SUCCESS", phase="SUCCESS")
                await progress_callback({
                    "event": "TASK_COMPLETED", "node_id": node_id,
                    "status": "SUCCESS", "progress": 100,
                })
                return
            last_error = result.stderr.strip() or result.stdout.strip() or "Worker execution failed"
            await checkpoints.rollback()
            await progress_callback({
                "event": "TASK_RETRYING", "node_id": node_id,
                "status": "RUNNING", "attempt": attempt, "error": last_error,
            })

        self.database.update_spec_status(node_id, "FAILED", last_error, phase="FAILED")
        await progress_callback({
            "event": "TASK_COMPLETED", "node_id": node_id,
            "status": "FAILED", "error": last_error, "progress": 100,
        })

    async def _run_command(
        self,
        workspace: Path,
        command: list[str],
        progress_callback: ProgressCallback,
        node_id: str,
    ) -> CommandResult:
        process = await asyncio.create_subprocess_exec(
            *command, cwd=workspace,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        registry.track(node_id, process)
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        async def consume_stdout() -> None:
            assert process.stdout is not None
            while True:
                if registry.is_cancelled(node_id):
                    break
                line = await process.stdout.readline()
                if not line:
                    break
                text = line.decode(errors="ignore")
                stdout_chunks.append(text)
                progress = self._extract_progress(text)
                if progress is not None:
                    await progress_callback({
                        "event": "TASK_PROGRESS", "node_id": node_id,
                        "status": "RUNNING", "progress": progress,
                    })

        async def consume_stderr() -> None:
            assert process.stderr is not None
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                stderr_chunks.append(line.decode(errors="ignore"))

        await asyncio.gather(consume_stdout(), consume_stderr())
        if registry.is_cancelled(node_id) and process.returncode is None:
            process.terminate()
            await process.wait()
        returncode = process.returncode if process.returncode is not None else await process.wait()
        return CommandResult(returncode, "".join(stdout_chunks), "".join(stderr_chunks))

    @staticmethod
    def _extract_progress(output: str) -> int | None:
        match = _PROGRESS_RE.search(output)
        if not match:
            return None
        total = int(match.group("total"))
        if total <= 0:
            return None
        return min(100, int(int(match.group("passed")) / total * 100))
