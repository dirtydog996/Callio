"""Unit tests for callio.voice.context_updater.refresh_system_prompt."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

# Stub heavy optional dependencies
for _stub in ("openai", "chromadb", "fastapi", "starlette", "pipecat"):
    if _stub not in sys.modules:
        _m = MagicMock()
        _m.__spec__ = None
        sys.modules[_stub] = _m

_openai = sys.modules["openai"]
if not hasattr(_openai, "AsyncOpenAI"):
    _openai.AsyncOpenAI = MagicMock()

# Stub callio.voice package to prevent loading pipeline.py
_voice_pkg = MagicMock()
_voice_pkg.__path__ = [str(pathlib.Path(__file__).parent.parent / "callio" / "voice")]
_voice_pkg.__package__ = "callio.voice"
sys.modules["callio.voice"] = _voice_pkg


def _load_voice_mod(name: str):
    """Load a callio.voice.* module directly, bypassing the package __init__."""
    base = pathlib.Path(__file__).parent.parent / "callio" / "voice"
    spec = importlib.util.spec_from_file_location(f"callio.voice.{name}", base / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[f"callio.voice.{name}"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Load the module dependency chain manually
_load_voice_mod("prompt")
_load_voice_mod("resume_context")
_load_voice_mod("memory_context")
_cu_mod = _load_voice_mod("context_updater")
refresh_system_prompt = _cu_mod.refresh_system_prompt

from callio.config.settings import Settings


class _FakeLLMContext:
    def __init__(self, messages: list | None = None) -> None:
        self.messages: list[dict[str, str]] = messages or []


class _FakeOrchestrator:
    def __init__(self, progress_text: str = "") -> None:
        self.database = MagicMock()
        self.progress = MagicMock()
        self.progress.build_context_block.return_value = progress_text


class ContextUpdaterTests(unittest.TestCase):
    def _settings(self, *, progress_inject: bool = True, memory_inject: bool = False) -> Settings:
        return Settings(progress_inject=progress_inject, memory_inject=memory_inject)

    # ------------------------------------------------------------------
    # no-op when both inject flags are off
    # ------------------------------------------------------------------
    def test_no_op_when_both_flags_disabled(self) -> None:
        ctx = _FakeLLMContext([{"role": "system", "content": "original"}])
        orchestrator = _FakeOrchestrator("new progress")
        settings = self._settings(progress_inject=False, memory_inject=False)
        refresh_system_prompt(ctx, orchestrator, "sess1", settings)
        self.assertEqual(ctx.messages[0]["content"], "original")

    # ------------------------------------------------------------------
    # injects system prompt into empty context
    # ------------------------------------------------------------------
    def test_creates_system_message_in_empty_context(self) -> None:
        ctx = _FakeLLMContext([])
        orchestrator = _FakeOrchestrator("progress block")
        settings = self._settings(progress_inject=True)
        refresh_system_prompt(ctx, orchestrator, "sess1", settings)
        self.assertEqual(len(ctx.messages), 1)
        self.assertEqual(ctx.messages[0]["role"], "system")
        self.assertIsInstance(ctx.messages[0]["content"], str)

    # ------------------------------------------------------------------
    # updates existing system message
    # ------------------------------------------------------------------
    def test_updates_existing_system_message(self) -> None:
        old_prompt = "old system prompt"
        ctx = _FakeLLMContext([{"role": "system", "content": old_prompt}])
        orchestrator = _FakeOrchestrator("new progress info")
        settings = self._settings(progress_inject=True)
        refresh_system_prompt(ctx, orchestrator, "sess1", settings)
        # System message should be updated, not duplicated
        system_msgs = [m for m in ctx.messages if m["role"] == "system"]
        self.assertEqual(len(system_msgs), 1)
        self.assertNotEqual(system_msgs[0]["content"], old_prompt)

    # ------------------------------------------------------------------
    # inserts system message before user messages if none exists
    # ------------------------------------------------------------------
    def test_inserts_system_before_user_messages(self) -> None:
        ctx = _FakeLLMContext([
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ])
        orchestrator = _FakeOrchestrator("progress")
        settings = self._settings(progress_inject=True)
        refresh_system_prompt(ctx, orchestrator, "sess1", settings)
        self.assertEqual(ctx.messages[0]["role"], "system")
        # User messages preserved
        self.assertEqual(ctx.messages[1]["role"], "user")
        self.assertEqual(ctx.messages[2]["role"], "assistant")

    # ------------------------------------------------------------------
    # progress block is included in refreshed prompt
    # ------------------------------------------------------------------
    def test_progress_block_included_in_prompt(self) -> None:
        ctx = _FakeLLMContext([{"role": "system", "content": "old"}])
        progress_text = "【任务进度】feature_a: RUNNING"
        orchestrator = _FakeOrchestrator(progress_text)
        settings = self._settings(progress_inject=True)
        refresh_system_prompt(ctx, orchestrator, "sess1", settings)
        self.assertIn(progress_text, ctx.messages[0]["content"])

    # ------------------------------------------------------------------
    # progress block NOT included when progress_inject is off
    # ------------------------------------------------------------------
    def test_progress_block_skipped_when_inject_off(self) -> None:
        ctx = _FakeLLMContext([{"role": "system", "content": "original prompt text"}])
        progress_text = "should not appear"
        orchestrator = _FakeOrchestrator(progress_text)
        settings = self._settings(progress_inject=False, memory_inject=True)
        mock_hub = MagicMock()
        mock_hub.search_semantic_memory.return_value = []
        # memory_inject=True but no memory results → still does the refresh
        refresh_system_prompt(ctx, orchestrator, "sess1", settings, memory_hub=mock_hub)
        self.assertNotIn(progress_text, ctx.messages[0]["content"])

    # ------------------------------------------------------------------
    # memory block integration (memory_inject=True)
    # ------------------------------------------------------------------
    def test_memory_block_included_when_inject_on(self) -> None:
        ctx = _FakeLLMContext([{"role": "system", "content": "original"}])
        orchestrator = _FakeOrchestrator("")
        settings = self._settings(progress_inject=False, memory_inject=True)

        mock_hub = MagicMock()
        mock_hub.search_semantic_memory.return_value = [
            {"content": "User prefers TypeScript"}
        ]
        orchestrator.database.get_session.return_value = {}
        orchestrator.database.list_sessions.return_value = []

        refresh_system_prompt(ctx, orchestrator, "sess1", settings, memory_hub=mock_hub)
        # Semantic memory should be referenced in the system prompt
        self.assertIn("TypeScript", ctx.messages[0]["content"])

    # ------------------------------------------------------------------
    # memory_inject=True but hub=None → still runs without error
    # ------------------------------------------------------------------
    def test_no_crash_when_memory_hub_is_none(self) -> None:
        ctx = _FakeLLMContext([{"role": "system", "content": "orig"}])
        orchestrator = _FakeOrchestrator("progress")
        settings = self._settings(progress_inject=True, memory_inject=True)
        refresh_system_prompt(ctx, orchestrator, "sess1", settings, memory_hub=None)
        self.assertEqual(ctx.messages[0]["role"], "system")

    # ------------------------------------------------------------------
    # Preserve history messages after system message
    # ------------------------------------------------------------------
    def test_history_messages_preserved_after_refresh(self) -> None:
        ctx = _FakeLLMContext([
            {"role": "system", "content": "old"},
            {"role": "user", "content": "turn1"},
            {"role": "assistant", "content": "reply1"},
        ])
        orchestrator = _FakeOrchestrator("new progress")
        settings = self._settings(progress_inject=True)
        refresh_system_prompt(ctx, orchestrator, "sess1", settings)
        self.assertEqual(len(ctx.messages), 3)
        self.assertEqual(ctx.messages[1], {"role": "user", "content": "turn1"})
        self.assertEqual(ctx.messages[2], {"role": "assistant", "content": "reply1"})


if __name__ == "__main__":
    unittest.main()
