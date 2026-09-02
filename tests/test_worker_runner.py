"""Unit tests for callio.worker.runner (WorkerRunner, GitCheckpointManager, CommandResult)."""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

for _stub in ("openai", "pipecat", "chromadb"):
    if _stub not in sys.modules:
        _m = MagicMock()
        _m.__spec__ = None
        sys.modules[_stub] = _m

_openai = sys.modules["openai"]
if not hasattr(_openai, "AsyncOpenAI"):
    _openai.AsyncOpenAI = MagicMock()


class TestCommandResult(unittest.TestCase):
    def test_defaults(self):
        from callio.worker.runner import CommandResult
        r = CommandResult(returncode=0, stdout="ok", stderr="")
        self.assertFalse(r.timed_out)

    def test_timed_out(self):
        from callio.worker.runner import CommandResult
        r = CommandResult(returncode=-1, stdout="", stderr="timeout", timed_out=True)
        self.assertTrue(r.timed_out)


class TestExtractProgress(unittest.TestCase):
    def test_standard_format(self):
        from callio.worker.runner import WorkerRunner
        self.assertEqual(WorkerRunner._extract_progress("5 passed tests, 10 total"), 50)

    def test_passed_only(self):
        from callio.worker.runner import WorkerRunner
        self.assertEqual(WorkerRunner._extract_progress("3 passed, 4 total"), 75)

    def test_all_passed(self):
        from callio.worker.runner import WorkerRunner
        self.assertEqual(WorkerRunner._extract_progress("10 passed tests. 10 total"), 100)

    def test_no_match(self):
        from callio.worker.runner import WorkerRunner
        self.assertIsNone(WorkerRunner._extract_progress("building project..."))

    def test_zero_total(self):
        from callio.worker.runner import WorkerRunner
        self.assertIsNone(WorkerRunner._extract_progress("0 passed, 0 total"))

    def test_capped_at_100(self):
        from callio.worker.runner import WorkerRunner
        result = WorkerRunner._extract_progress("15 passed tests, 10 total")
        self.assertEqual(result, 100)

    def test_case_insensitive(self):
        from callio.worker.runner import WorkerRunner
        self.assertEqual(WorkerRunner._extract_progress("5 PASSED, 10 TOTAL"), 50)


class TestGitCheckpointManager(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.settings = MagicMock()
        self.settings.enable_git_resets = True

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_save_no_git_dir(self):
        from callio.worker.runner import GitCheckpointManager
        mgr = GitCheckpointManager(self.workspace, self.settings)
        result = asyncio.run(mgr.save("node1", 1))
        self.assertIsNone(result)
        self.assertIsNone(mgr.last_checkpoint)

    def test_rollback_skipped_without_checkpoint(self):
        from callio.worker.runner import GitCheckpointManager
        mgr = GitCheckpointManager(self.workspace, self.settings)
        mgr.last_checkpoint = None
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            asyncio.run(mgr.rollback())
            mock_exec.assert_not_called()

    def test_rollback_skipped_when_git_disabled(self):
        from callio.worker.runner import GitCheckpointManager
        self.settings.enable_git_resets = False
        mgr = GitCheckpointManager(self.workspace, self.settings)
        mgr.last_checkpoint = Path("/fake/diff")
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            asyncio.run(mgr.rollback())
            mock_exec.assert_not_called()

    def test_rollback_skipped_when_git_dir_removed(self):
        from callio.worker.runner import GitCheckpointManager
        mgr = GitCheckpointManager(self.workspace, self.settings)
        mgr.last_checkpoint = Path("/fake/diff")
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            asyncio.run(mgr.rollback())
            mock_exec.assert_not_called()

    def test_save_with_git_dir(self):
        from callio.worker.runner import GitCheckpointManager
        (self.workspace / ".git").mkdir()
        mgr = GitCheckpointManager(self.workspace, self.settings)
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"diff content", b""))
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = asyncio.run(mgr.save("node1", 1))
        self.assertIsNotNone(result)
        self.assertTrue(result.exists())
        self.assertEqual(result.read_bytes(), b"diff content")
        self.assertEqual(mgr.last_checkpoint, result)

    def test_rollback_with_checkpoint(self):
        from callio.worker.runner import GitCheckpointManager
        (self.workspace / ".git").mkdir()
        mgr = GitCheckpointManager(self.workspace, self.settings)
        mgr.last_checkpoint = Path("/fake/diff")
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            asyncio.run(mgr.rollback())
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            self.assertIn("git", args)
            self.assertIn("reset", args)
            self.assertIn("--hard", args)


class TestWorkerRunnerExecute(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.settings = MagicMock()
        self.settings.task_timeout_sec = 3600
        self.settings.execute_max_retries = 3
        self.settings.enable_git_resets = False
        self.settings.sandbox_root = self.tmpdir.name
        self.settings.sandbox_use_docker = False
        self.database = MagicMock()
        self.progress_cb = AsyncMock()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_resolve_failure_marks_failed(self):
        from callio.worker.runner import WorkerRunner
        with patch("callio.worker.runner.AgentResolver") as MockResolver, \
             patch("callio.worker.runner.SandboxManager"):
            MockResolver.return_value.resolve.return_value = None
            MockResolver.return_value.missing_message.return_value = "no agent"
            runner = WorkerRunner(self.database, self.settings)
            asyncio.run(runner.execute("node1", "do stuff", self.progress_cb))
            self.database.update_spec_status.assert_any_call("node1", "FAILED", "no agent", phase="FAILED")
            self.progress_cb.assert_awaited()

    def test_success_on_first_attempt(self):
        from callio.worker.runner import WorkerRunner, CommandResult
        with patch("callio.worker.runner.AgentResolver") as MockResolver, \
             patch("callio.worker.runner.SandboxManager") as MockSandbox, \
             patch("callio.worker.runner.GitCheckpointManager") as MockCheckpoint, \
             patch("callio.worker.runner.registry") as mock_registry:
            MockResolver.return_value.resolve.return_value = MagicMock(
                backend="echo", argv=["echo", "hello"]
            )
            MockResolver.return_value.missing_message.return_value = ""
            MockSandbox.return_value.prepare_workspace.return_value = MagicMock(
                workspace=Path(self.tmpdir.name)
            )
            MockCheckpoint.return_value.save = AsyncMock(return_value=None)
            MockCheckpoint.return_value.rollback = AsyncMock()
            mock_registry.is_cancelled.return_value = False
            runner = WorkerRunner(self.database, self.settings)
            runner._run_command = AsyncMock(return_value=CommandResult(0, "done", "", False))
            asyncio.run(runner.execute("node1", "echo hello", self.progress_cb))
            self.database.update_spec_status.assert_any_call("node1", "SUCCESS", phase="SUCCESS")
            runner._run_command.assert_awaited_once()

    def test_retry_on_failure_then_success(self):
        from callio.worker.runner import WorkerRunner, CommandResult
        with patch("callio.worker.runner.AgentResolver") as MockResolver, \
             patch("callio.worker.runner.SandboxManager") as MockSandbox, \
             patch("callio.worker.runner.GitCheckpointManager") as MockCheckpoint, \
             patch("callio.worker.runner.registry") as mock_registry:
            MockResolver.return_value.resolve.return_value = MagicMock(
                backend="echo", argv=["echo", "fail"]
            )
            MockSandbox.return_value.prepare_workspace.return_value = MagicMock(
                workspace=Path(self.tmpdir.name)
            )
            MockCheckpoint.return_value.save = AsyncMock(return_value=None)
            MockCheckpoint.return_value.rollback = AsyncMock()
            mock_registry.is_cancelled.return_value = False
            runner = WorkerRunner(self.database, self.settings)
            runner._run_command = AsyncMock(
                side_effect=[
                    CommandResult(1, "", "error1", False),
                    CommandResult(0, "ok", "", False),
                ]
            )
            asyncio.run(runner.execute("node1", "task", self.progress_cb))
            self.database.update_spec_status.assert_any_call("node1", "SUCCESS", phase="SUCCESS")
            self.assertEqual(runner._run_command.call_count, 2)

    def test_all_retries_exhausted(self):
        from callio.worker.runner import WorkerRunner, CommandResult
        self.settings.execute_max_retries = 2
        with patch("callio.worker.runner.AgentResolver") as MockResolver, \
             patch("callio.worker.runner.SandboxManager") as MockSandbox, \
             patch("callio.worker.runner.GitCheckpointManager") as MockCheckpoint, \
             patch("callio.worker.runner.registry") as mock_registry:
            MockResolver.return_value.resolve.return_value = MagicMock(
                backend="echo", argv=["echo", "fail"]
            )
            MockSandbox.return_value.prepare_workspace.return_value = MagicMock(
                workspace=Path(self.tmpdir.name)
            )
            MockCheckpoint.return_value.save = AsyncMock(return_value=None)
            MockCheckpoint.return_value.rollback = AsyncMock()
            mock_registry.is_cancelled.return_value = False
            runner = WorkerRunner(self.database, self.settings)
            runner._run_command = AsyncMock(
                return_value=CommandResult(1, "", "persistent error", False)
            )
            asyncio.run(runner.execute("node1", "task", self.progress_cb))
            self.database.update_spec_status.assert_any_call(
                "node1", "FAILED", "persistent error", phase="FAILED"
            )
            self.assertEqual(runner._run_command.call_count, 2)

    def test_timeout_treated_as_failure(self):
        from callio.worker.runner import WorkerRunner, CommandResult
        with patch("callio.worker.runner.AgentResolver") as MockResolver, \
             patch("callio.worker.runner.SandboxManager") as MockSandbox, \
             patch("callio.worker.runner.GitCheckpointManager") as MockCheckpoint, \
             patch("callio.worker.runner.registry") as mock_registry:
            MockResolver.return_value.resolve.return_value = MagicMock(
                backend="slow", argv=["sleep", "999"]
            )
            MockSandbox.return_value.prepare_workspace.return_value = MagicMock(
                workspace=Path(self.tmpdir.name)
            )
            MockCheckpoint.return_value.save = AsyncMock(return_value=None)
            MockCheckpoint.return_value.rollback = AsyncMock()
            mock_registry.is_cancelled.return_value = False
            runner = WorkerRunner(self.database, self.settings)
            runner._run_command = AsyncMock(
                return_value=CommandResult(-1, "", "", timed_out=True)
            )
            asyncio.run(runner.execute("node1", "slow task", self.progress_cb))
            self.database.update_spec_status.assert_any_call(
                "node1", "FAILED", unittest.mock.ANY, phase="FAILED"
            )

    def test_cancellation_during_execution(self):
        from callio.worker.runner import WorkerRunner, CommandResult
        with patch("callio.worker.runner.AgentResolver") as MockResolver, \
             patch("callio.worker.runner.SandboxManager") as MockSandbox, \
             patch("callio.worker.runner.GitCheckpointManager") as MockCheckpoint, \
             patch("callio.worker.runner.registry") as mock_registry:
            MockResolver.return_value.resolve.return_value = MagicMock(
                backend="echo", argv=["echo", "hi"]
            )
            MockSandbox.return_value.prepare_workspace.return_value = MagicMock(
                workspace=Path(self.tmpdir.name)
            )
            MockCheckpoint.return_value.save = AsyncMock(return_value=None)
            MockCheckpoint.return_value.rollback = AsyncMock()
            mock_registry.is_cancelled.side_effect = [False, True]
            runner = WorkerRunner(self.database, self.settings)
            runner._run_command = AsyncMock(
                return_value=CommandResult(0, "", "", False)
            )
            asyncio.run(runner.execute("node1", "task", self.progress_cb))
            self.database.update_spec_status.assert_any_call(
                "node1", "CANCELLED", "user cancelled", phase="CANCELLED"
            )


if __name__ == "__main__":
    unittest.main()
