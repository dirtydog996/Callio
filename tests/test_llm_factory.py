"""Unit tests for callio.llm.factory (build_chat_client).

Heavy optional dependencies (openai, pipecat, chromadb) are stubbed so
these tests run in a lean environment without any LLM infrastructure.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub heavy optional dependencies before any callio import
# ---------------------------------------------------------------------------
for _stub in ("openai", "pipecat", "chromadb"):
    if _stub not in sys.modules:
        _m = MagicMock()
        _m.__spec__ = None
        sys.modules[_stub] = _m

_openai = sys.modules["openai"]
if not hasattr(_openai, "AsyncOpenAI"):
    _openai.AsyncOpenAI = MagicMock()

# ---------------------------------------------------------------------------
# Now we can safely import callio modules
# ---------------------------------------------------------------------------
from callio.config.settings import Settings
from callio.llm.factory import build_chat_client


class _OpenAICallCapture:
    """Records the kwargs passed to each AsyncOpenAI() constructor call."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, *args, **kwargs):
        self.calls.append(kwargs)
        return MagicMock()

    def last_kwargs(self) -> dict:
        if not self.calls:
            raise AssertionError("AsyncOpenAI was never called")
        return self.calls[-1]


_FACTORY_PATH = "callio.llm.factory.AsyncOpenAI"


class BuildChatClientTests(unittest.TestCase):

    def _settings(self, **overrides) -> Settings:
        return Settings(**overrides)

    # ------------------------------------------------------------------
    # Default (ollama) provider
    # ------------------------------------------------------------------
    def test_ollama_uses_ollama_base_url(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(llm_provider="ollama", ollama_base_url="http://ollama:11434/v1")
            build_chat_client(s)
        kw = cap.last_kwargs()
        self.assertEqual(kw["base_url"], "http://ollama:11434/v1")
        self.assertEqual(kw["api_key"], "ollama")

    def test_ollama_prefers_llm_base_url_over_ollama_url(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(
                llm_provider="ollama",
                llm_base_url="http://custom:11434/v1",
                ollama_base_url="http://old:11434/v1",
            )
            build_chat_client(s)
        self.assertEqual(cap.last_kwargs()["base_url"], "http://custom:11434/v1")

    def test_default_provider_is_ollama(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(llm_provider="", ollama_base_url="http://default:11434/v1")
            build_chat_client(s)
        kw = cap.last_kwargs()
        self.assertIn("base_url", kw)
        self.assertEqual(kw["api_key"], "ollama")

    # ------------------------------------------------------------------
    # Backward-compat: ollama_base_url field still drives base_url
    # ------------------------------------------------------------------
    def test_backward_compat_ollama_base_url_respected(self) -> None:
        """ollama_base_url (CALLIO_OLLAMA_BASE_URL) is still used as default base URL."""
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(llm_provider="ollama", ollama_base_url="http://compat:11434/v1")
            build_chat_client(s)
        self.assertEqual(cap.last_kwargs()["base_url"], "http://compat:11434/v1")

    # ------------------------------------------------------------------
    # OpenAI provider
    # ------------------------------------------------------------------
    def test_openai_no_base_url(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(llm_provider="openai")
            build_chat_client(s)
        kw = cap.last_kwargs()
        self.assertNotIn("base_url", kw)

    def test_openai_explicit_api_key(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(llm_provider="openai", llm_api_key="sk-test-key")
            build_chat_client(s)
        self.assertEqual(cap.last_kwargs()["api_key"], "sk-test-key")

    def test_openai_no_explicit_key_passes_no_api_key_kwarg(self) -> None:
        """Let AsyncOpenAI read OPENAI_API_KEY from env on its own."""
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(llm_provider="openai", llm_api_key="")
            build_chat_client(s)
        self.assertNotIn("api_key", cap.last_kwargs())

    # ------------------------------------------------------------------
    # Anthropic provider (OpenAI-compat endpoint)
    # ------------------------------------------------------------------
    def test_anthropic_uses_anthropic_base_url(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(llm_provider="anthropic", llm_api_key="ant-key")
            build_chat_client(s)
        kw = cap.last_kwargs()
        self.assertIn("api.anthropic.com", kw["base_url"])
        self.assertEqual(kw["api_key"], "ant-key")

    def test_anthropic_reads_env_key(self) -> None:
        cap = _OpenAICallCapture()
        s = self._settings(llm_provider="anthropic", llm_api_key="")
        with patch(_FACTORY_PATH, cap), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-ant-key"}, clear=False):
            build_chat_client(s)
        self.assertEqual(cap.last_kwargs()["api_key"], "env-ant-key")

    def test_anthropic_explicit_base_url_override(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(
                llm_provider="anthropic",
                llm_api_key="k",
                llm_base_url="https://proxy.example.com/v1",
            )
            build_chat_client(s)
        self.assertEqual(cap.last_kwargs()["base_url"], "https://proxy.example.com/v1")

    # ------------------------------------------------------------------
    # Gemini provider (OpenAI-compat endpoint)
    # ------------------------------------------------------------------
    def test_gemini_uses_google_base_url(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(llm_provider="gemini", llm_api_key="gem-key")
            build_chat_client(s)
        kw = cap.last_kwargs()
        self.assertIn("googleapis.com", kw["base_url"])
        self.assertEqual(kw["api_key"], "gem-key")

    def test_gemini_reads_gemini_api_key_env(self) -> None:
        cap = _OpenAICallCapture()
        s = self._settings(llm_provider="gemini", llm_api_key="")
        with patch(_FACTORY_PATH, cap), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "env-gem"}, clear=False):
            build_chat_client(s)
        self.assertEqual(cap.last_kwargs()["api_key"], "env-gem")

    def test_gemini_reads_google_api_key_fallback(self) -> None:
        cap = _OpenAICallCapture()
        s = self._settings(llm_provider="gemini", llm_api_key="")
        env = {"GOOGLE_API_KEY": "ggl-key"}
        with patch(_FACTORY_PATH, cap), \
             patch.dict(os.environ, env, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            build_chat_client(s)
        self.assertEqual(cap.last_kwargs()["api_key"], "ggl-key")

    # ------------------------------------------------------------------
    # openai_compatible provider
    # ------------------------------------------------------------------
    def test_openai_compatible_uses_explicit_base_url(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(
                llm_provider="openai_compatible",
                llm_base_url="https://api.groq.com/openai/v1",
                llm_api_key="groq-key",
            )
            build_chat_client(s)
        kw = cap.last_kwargs()
        self.assertEqual(kw["base_url"], "https://api.groq.com/openai/v1")
        self.assertEqual(kw["api_key"], "groq-key")

    def test_openai_compatible_without_explicit_url_falls_back_to_ollama_url(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(
                llm_provider="openai_compatible",
                llm_base_url="",
                ollama_base_url="http://fallback:11434/v1",
            )
            build_chat_client(s)
        self.assertEqual(cap.last_kwargs()["base_url"], "http://fallback:11434/v1")

    # ------------------------------------------------------------------
    # Unknown/custom provider falls back to generic compat path
    # ------------------------------------------------------------------
    def test_unknown_provider_uses_ollama_base_url(self) -> None:
        cap = _OpenAICallCapture()
        with patch(_FACTORY_PATH, cap):
            s = self._settings(
                llm_provider="my_custom_provider",
                ollama_base_url="http://custom:8080/v1",
            )
            build_chat_client(s)
        self.assertEqual(cap.last_kwargs()["base_url"], "http://custom:8080/v1")


if __name__ == "__main__":
    unittest.main()
