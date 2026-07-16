"""Unit tests for callio.worker.agent_resolver."""
from __future__ import annotations

import shutil
import unittest
from unittest.mock import patch

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Stub heavy optional dependencies before importing callio.worker
for _stub in ("openai", "pipecat", "chromadb"):
    if _stub not in sys.modules:
        _m = MagicMock()
        _m.__spec__ = None
        sys.modules[_stub] = _m
        # Ensure sub-attribute imports resolve to mocks
        sys.modules[f"{_stub}.AsyncOpenAI"] = _m

# openai.AsyncOpenAI specifically
_openai = sys.modules["openai"]
if not hasattr(_openai, "AsyncOpenAI"):
    _openai.AsyncOpenAI = MagicMock()

from callio.config.settings import Settings
from callio.worker.agent_resolver import AgentResolver, ResolvedAgent, _DETECT_ORDER, _TEMPLATES


class AgentResolverTests(unittest.TestCase):
    def _settings(self, **kwargs) -> Settings:
        base = dict(agent_backend="", agent_command="")
        base.update(kwargs)
        return Settings(**base)

    # ------------------------------------------------------------------
    # CALLIO_AGENT_BACKEND explicit override
    # ------------------------------------------------------------------
    def test_explicit_backend_hermes(self) -> None:
        settings = self._settings(agent_backend="hermes")
        resolver = AgentResolver(settings)
        with patch("shutil.which", return_value="/usr/bin/hermes"):
            result = resolver.resolve("add login page")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.backend, "hermes")
        self.assertIn("add login page", result.argv)

    def test_explicit_backend_openclaw(self) -> None:
        settings = self._settings(agent_backend="openclaw")
        resolver = AgentResolver(settings)
        with patch("shutil.which", return_value="/usr/bin/openclaw"):
            result = resolver.resolve("fix tests")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.backend, "openclaw")
        self.assertIn("fix tests", result.argv)

    def test_backend_not_installed_returns_none(self) -> None:
        settings = self._settings(agent_backend="hermes")
        resolver = AgentResolver(settings)
        with patch("shutil.which", return_value=None):
            result = resolver.resolve("task")
        self.assertIsNone(result)

    def test_unknown_backend_returns_none(self) -> None:
        settings = self._settings(agent_backend="nonexistent_agent")
        resolver = AgentResolver(settings)
        with patch("shutil.which", return_value=None):
            result = resolver.resolve("task")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # CALLIO_AGENT_COMMAND custom command
    # ------------------------------------------------------------------
    def test_custom_command_with_task_placeholder(self) -> None:
        settings = self._settings(agent_command="myagent run {task} --verbose")
        resolver = AgentResolver(settings)
        with patch("shutil.which", return_value="/usr/bin/myagent"):
            result = resolver.resolve("write tests")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.backend, "custom")
        self.assertIn("write tests", result.argv)
        self.assertNotIn("{task}", result.argv)

    def test_custom_command_without_placeholder_appends_task(self) -> None:
        settings = self._settings(agent_command="myagent run")
        resolver = AgentResolver(settings)
        with patch("shutil.which", return_value="/usr/bin/myagent"):
            result = resolver.resolve("fix bug")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.argv[-1], "fix bug")

    def test_custom_command_not_found_returns_none(self) -> None:
        settings = self._settings(agent_command="ghost_agent {task}")
        resolver = AgentResolver(settings)
        with patch("shutil.which", return_value=None):
            result = resolver.resolve("task")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Auto-detection order
    # ------------------------------------------------------------------
    def test_autodetect_picks_first_available(self) -> None:
        settings = self._settings()
        resolver = AgentResolver(settings)
        first = _DETECT_ORDER[0]

        def which_only_first(name: str) -> str | None:
            return f"/usr/bin/{first}" if name == first else None

        with patch("shutil.which", side_effect=which_only_first):
            result = resolver.resolve("task")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.backend, first)

    def test_autodetect_no_agent_returns_none(self) -> None:
        settings = self._settings()
        resolver = AgentResolver(settings)
        with patch("shutil.which", return_value=None):
            result = resolver.resolve("task")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # daily flag uses _DAILY_TEMPLATES
    # ------------------------------------------------------------------
    def test_daily_flag_changes_template(self) -> None:
        settings = self._settings(agent_backend="claude")
        resolver = AgentResolver(settings)
        with patch("shutil.which", return_value="/usr/bin/claude"):
            code_result = resolver.resolve("task", daily=False)
            daily_result = resolver.resolve("task", daily=True)
        # code template: ["claude", "code", "{task}"]
        # daily template: ["claude", "{task}"]
        assert code_result is not None
        assert daily_result is not None
        self.assertIn("code", code_result.argv)
        self.assertNotIn("code", daily_result.argv)

    # ------------------------------------------------------------------
    # missing_message
    # ------------------------------------------------------------------
    def test_missing_message_mentions_backends(self) -> None:
        resolver = AgentResolver(self._settings())
        msg = resolver.missing_message()
        for name in _DETECT_ORDER:
            self.assertIn(name, msg)

    # ------------------------------------------------------------------
    # ResolvedAgent is frozen
    # ------------------------------------------------------------------
    def test_resolved_agent_is_frozen(self) -> None:
        agent = ResolvedAgent(argv=["cmd", "arg"], backend="test")
        with self.assertRaises((AttributeError, TypeError)):
            agent.backend = "other"  # type: ignore[misc]

    # ------------------------------------------------------------------
    # task description is embedded verbatim
    # ------------------------------------------------------------------
    def test_task_with_special_characters(self) -> None:
        settings = self._settings(agent_backend="aider")
        resolver = AgentResolver(settings)
        task = "Fix bug: handle 'None' in user/profile & reset cache"
        with patch("shutil.which", return_value="/usr/bin/aider"):
            result = resolver.resolve(task)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn(task, result.argv)


if __name__ == "__main__":
    unittest.main()
