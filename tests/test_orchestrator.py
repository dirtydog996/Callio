"""Unit tests for callio.orchestrator modules."""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

for _stub in ("openai", "pipecat", "chromadb"):
    if _stub not in sys.modules:
        _m = MagicMock()
        _m.__spec__ = None
        sys.modules[_stub] = _m

_openai = sys.modules["openai"]
if not hasattr(_openai, "AsyncOpenAI"):
    _openai.AsyncOpenAI = MagicMock()


class _BaseDB:
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        from callio.config.settings import Settings
        from callio.core.database import Database
        from callio.core.session_events import SessionEventStore
        from callio.orchestrator.event_bus import EventBus

        self.settings = Settings(db_path=str(Path(self.tmpdir.name) / "test.db"))
        self.database = Database(self.settings)
        self.database.initialize()
        self.broadcast = AsyncMock()
        self.events = SessionEventStore(self.database)
        self.event_bus = EventBus(self.database, self.events, self.broadcast)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _make_session(self, session_id: str = "sess1") -> str:
        self.database.create_session(session_id, "Test Session")
        return session_id


class TestEventBus(_BaseDB, unittest.TestCase):
    def test_emit_appends_and_broadcasts(self):
        asyncio.run(self.event_bus.emit("s1", "TASK_PROPOSED", {"node_id": "n1"}))
        events = self.events.list_for_session("s1", limit=10)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "TASK_PROPOSED")
        self.broadcast.assert_awaited_once()

    def test_emit_broadcast_failure_does_not_raise(self):
        self.broadcast.side_effect = RuntimeError("network down")
        asyncio.run(self.event_bus.emit("s1", "TASK_PROPOSED", {"node_id": "n1"}))
        events = self.events.list_for_session("s1", limit=10)
        self.assertEqual(len(events), 1)

    def test_emit_message_contains_event_and_session(self):
        asyncio.run(self.event_bus.emit("s2", "SESSION_STARTED", {"title": "hello"}))
        msg = self.broadcast.call_args[0][0]
        self.assertEqual(msg["event"], "SESSION_STARTED")
        self.assertEqual(msg["session_id"], "s2")
        self.assertEqual(msg["title"], "hello")


class TestSessionRegistry(_BaseDB, unittest.TestCase):
    def test_open_new_session(self):
        from callio.orchestrator.session_registry import SessionRegistry
        reg = SessionRegistry(self.database, self.event_bus)
        ctx = reg.open(101)
        self.assertIsNotNone(ctx.session_id)
        self.assertFalse(ctx.resumed)
        session = self.database.get_session(ctx.session_id)
        self.assertIsNotNone(session)

    def test_open_resume_existing_session(self):
        self.database.create_session("existing-sess", "Previous Chat")
        from callio.orchestrator.session_registry import SessionRegistry
        reg = SessionRegistry(self.database, self.event_bus)
        ctx = reg.open(202, resume_session_id="existing-sess")
        self.assertEqual(ctx.session_id, "existing-sess")
        self.assertTrue(ctx.resumed)
        self.assertEqual(ctx.title, "Previous Chat")

    def test_get_returns_active_context(self):
        from callio.orchestrator.session_registry import SessionRegistry
        reg = SessionRegistry(self.database, self.event_bus)
        ctx = reg.open(303)
        retrieved = reg.get(303)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.session_id, ctx.session_id)

    def test_get_returns_none_for_unknown(self):
        from callio.orchestrator.session_registry import SessionRegistry
        reg = SessionRegistry(self.database, self.event_bus)
        self.assertIsNone(reg.get(999))

    def test_finalize_removes_from_active(self):
        from callio.orchestrator.session_registry import SessionRegistry
        reg = SessionRegistry(self.database, self.event_bus)
        ctx = reg.open(404)
        result = asyncio.run(reg.finalize(404, transcript="user: hello"))
        self.assertIsNotNone(result)
        self.assertEqual(result.session_id, ctx.session_id)
        self.assertIsNone(reg.get(404))
        session = self.database.get_session(ctx.session_id)
        self.assertIn("hello", session.get("transcript", ""))

    def test_finalize_unknown_connection(self):
        from callio.orchestrator.session_registry import SessionRegistry
        reg = SessionRegistry(self.database, self.event_bus)
        result = asyncio.run(reg.finalize(999))
        self.assertIsNone(result)


class TestTranscriptBuffer(_BaseDB, unittest.TestCase):
    def test_append_and_get(self):
        from callio.orchestrator.transcript_buffer import TranscriptBuffer
        buf = TranscriptBuffer(self.database, self.event_bus, self.settings)
        buf.append("s1", "user", "hello world")
        buf.append("s1", "assistant", "hi there")
        text = buf.get_transcript("s1")
        self.assertIn("user: hello world", text)
        self.assertIn("assistant: hi there", text)

    def test_append_empty_skipped(self):
        from callio.orchestrator.transcript_buffer import TranscriptBuffer
        buf = TranscriptBuffer(self.database, self.event_bus, self.settings)
        buf.append("s1", "user", "  ")
        self.assertEqual(buf.get_transcript("s1"), "")

    def test_get_empty_session(self):
        from callio.orchestrator.transcript_buffer import TranscriptBuffer
        buf = TranscriptBuffer(self.database, self.event_bus, self.settings)
        self.assertEqual(buf.get_transcript("nonexistent"), "")

    def test_hydrate(self):
        from callio.orchestrator.transcript_buffer import TranscriptBuffer
        buf = TranscriptBuffer(self.database, self.event_bus, self.settings)
        transcript = "user: question\nassistant: answer\nuser: followup"
        buf.hydrate("s1", transcript)
        self.assertEqual(buf.get_transcript("s1"), transcript)
        self.assertEqual(buf._turn_counts["s1"], 2)

    def test_flush_persists_transcript(self):
        self._make_session("s1")
        from callio.orchestrator.transcript_buffer import TranscriptBuffer
        buf = TranscriptBuffer(self.database, self.event_bus, self.settings)
        buf.append("s1", "user", "test message")
        transcript = asyncio.run(buf.flush("s1"))
        self.assertIn("test message", transcript)
        session = self.database.get_session("s1")
        self.assertIn("test message", session.get("transcript", ""))


class TestTaskProposal(_BaseDB, unittest.TestCase):
    def test_propose_creates_tasks(self):
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        proposal = TaskProposal(self.database, self.event_bus)
        result = asyncio.run(proposal.propose("s1", [
            {"title": "Task A", "description": "do A", "kind": "EXECUTE"},
            {"title": "Task B", "description": "do B", "kind": "ANALYZE"},
        ]))
        self.assertEqual(len(result["tasks"]), 2)
        nodes = self.database.list_spec_nodes(session_id="s1")
        self.assertEqual(len(nodes), 2)
        self.broadcast.assert_awaited()

    def test_propose_default_kind(self):
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        proposal = TaskProposal(self.database, self.event_bus)
        result = asyncio.run(proposal.propose("s1", [
            {"title": "No Kind", "description": "no kind field"},
        ]))
        self.assertEqual(result["tasks"][0]["kind"], "EXECUTE")

    def test_propose_invalid_kind_falls_back(self):
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        proposal = TaskProposal(self.database, self.event_bus)
        result = asyncio.run(proposal.propose("s1", [
            {"title": "Bad Kind", "description": "test", "kind": "INVALID"},
        ]))
        self.assertEqual(result["tasks"][0]["kind"], "EXECUTE")

    def test_cancel_proposed_tasks(self):
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        proposal = TaskProposal(self.database, self.event_bus)
        result = asyncio.run(proposal.propose("s1", [
            {"title": "Task A", "description": "do A"},
        ]))
        node_id = result["tasks"][0]["node_id"]
        cancel_result = asyncio.run(proposal.cancel("s1", [node_id]))
        self.assertEqual(len(cancel_result["cancelled"]), 1)
        node = self.database.get_spec_node(node_id)
        self.assertEqual(node["status"], "CANCELLED")

    def test_cancel_skips_non_proposed(self):
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        proposal = TaskProposal(self.database, self.event_bus)
        result = asyncio.run(proposal.propose("s1", [
            {"title": "Task A", "description": "do A"},
        ]))
        node_id = result["tasks"][0]["node_id"]
        self.database.update_spec_status(node_id, "PENDING", phase="CONFIRMED")
        cancel_result = asyncio.run(proposal.cancel("s1", [node_id]))
        self.assertEqual(len(cancel_result["cancelled"]), 0)

    def test_cancel_skips_other_session(self):
        self._make_session("s1")
        self._make_session("s2")
        from callio.orchestrator.task_proposal import TaskProposal
        proposal = TaskProposal(self.database, self.event_bus)
        result = asyncio.run(proposal.propose("s1", [
            {"title": "Task A", "description": "do A"},
        ]))
        node_id = result["tasks"][0]["node_id"]
        cancel_result = asyncio.run(proposal.cancel("s2", [node_id]))
        self.assertEqual(len(cancel_result["cancelled"]), 0)


class TestTaskCoordinator(_BaseDB, unittest.TestCase):
    def test_confirm_dispatches_tasks(self):
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        from callio.orchestrator.task_coordinator import TaskCoordinator
        proposal = TaskProposal(self.database, self.event_bus)
        result = asyncio.run(proposal.propose("s1", [
            {"title": "Task A", "description": "do A"},
        ]))
        node_id = result["tasks"][0]["node_id"]
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock()
        coord = TaskCoordinator(self.database, self.event_bus, dispatcher, self.settings)
        confirm_result = asyncio.run(coord.confirm("s1", [node_id]))
        self.assertEqual(len(confirm_result["confirmed"]), 1)
        node = self.database.get_spec_node(node_id)
        self.assertEqual(node["phase"], "CONFIRMED")
        dispatcher.dispatch.assert_awaited_once()

    def test_confirm_all(self):
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        from callio.orchestrator.task_coordinator import TaskCoordinator
        proposal = TaskProposal(self.database, self.event_bus)
        asyncio.run(proposal.propose("s1", [
            {"title": "Task A", "description": "do A"},
            {"title": "Task B", "description": "do B"},
        ]))
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock()
        coord = TaskCoordinator(self.database, self.event_bus, dispatcher, self.settings)
        result = asyncio.run(coord.confirm("s1", confirm_all=True))
        self.assertEqual(len(result["confirmed"]), 2)

    def test_confirm_no_tasks(self):
        self._make_session("s1")
        from callio.orchestrator.task_coordinator import TaskCoordinator
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock()
        coord = TaskCoordinator(self.database, self.event_bus, dispatcher, self.settings)
        result = asyncio.run(coord.confirm("s1", []))
        self.assertEqual(len(result["confirmed"]), 0)

    def test_confirm_skips_non_proposed(self):
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        from callio.orchestrator.task_coordinator import TaskCoordinator
        proposal = TaskProposal(self.database, self.event_bus)
        result = asyncio.run(proposal.propose("s1", [
            {"title": "Task A", "description": "do A"},
        ]))
        node_id = result["tasks"][0]["node_id"]
        self.database.update_spec_status(node_id, "PENDING", phase="CONFIRMED")
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock()
        coord = TaskCoordinator(self.database, self.event_bus, dispatcher, self.settings)
        confirm_result = asyncio.run(coord.confirm("s1", [node_id]))
        self.assertEqual(len(confirm_result["confirmed"]), 0)

    def test_confirm_respects_parallel_limit(self):
        self.settings.max_parallel_tasks = 1
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        from callio.orchestrator.task_coordinator import TaskCoordinator
        proposal = TaskProposal(self.database, self.event_bus)
        asyncio.run(proposal.propose("s1", [
            {"title": "Task A", "description": "do A"},
            {"title": "Task B", "description": "do B"},
        ]))
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock()
        coord = TaskCoordinator(self.database, self.event_bus, dispatcher, self.settings)
        result = asyncio.run(coord.confirm("s1", confirm_all=True))
        self.assertEqual(len(result["confirmed"]), 1)


class TestProgressSnapshot(_BaseDB, unittest.TestCase):
    def test_snapshot_empty_session(self):
        self._make_session("s1")
        from callio.orchestrator.progress_snapshot import ProgressSnapshot
        prog = ProgressSnapshot(self.database, self.settings)
        snap = prog.snapshot("s1")
        self.assertEqual(snap["proposed"], [])
        self.assertEqual(snap["active"], [])
        self.assertEqual(snap["done"], [])

    def test_snapshot_with_tasks(self):
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        from callio.orchestrator.progress_snapshot import ProgressSnapshot
        proposal = TaskProposal(self.database, self.event_bus)
        asyncio.run(proposal.propose("s1", [
            {"title": "Task A", "description": "do A"},
        ]))
        prog = ProgressSnapshot(self.database, self.settings)
        snap = prog.snapshot("s1")
        self.assertEqual(len(snap["proposed"]), 1)
        self.assertEqual(snap["proposed"][0]["title"], "Task A")
        self.assertIn(snap["counts"].get("DRAFT", 0), [1])

    def test_build_context_block_disabled(self):
        self.settings.progress_inject = False
        self._make_session("s1")
        from callio.orchestrator.progress_snapshot import ProgressSnapshot
        prog = ProgressSnapshot(self.database, self.settings)
        self.assertEqual(prog.build_context_block("s1"), "")

    def test_build_context_block_with_tasks(self):
        self.settings.progress_inject = True
        self._make_session("s1")
        from callio.orchestrator.task_proposal import TaskProposal
        from callio.orchestrator.progress_snapshot import ProgressSnapshot
        proposal = TaskProposal(self.database, self.event_bus)
        asyncio.run(proposal.propose("s1", [
            {"title": "Task A", "description": "do A"},
        ]))
        prog = ProgressSnapshot(self.database, self.settings)
        block = prog.build_context_block("s1")
        self.assertIn("[Background Task Status]", block)
        self.assertIn("Task A", block)


if __name__ == "__main__":
    unittest.main()
