"""Chat completion client factory for worker runners.

All supported providers ultimately return an ``AsyncOpenAI``-compatible
client so that existing runner code can call
``client.chat.completions.create(...)`` without changes.

Provider routing
----------------
``CALLIO_LLM_PROVIDER`` (``settings.llm_provider``) selects the backend:

* ``ollama``  (default) — Ollama local inference via OpenAI-compat API.
  Uses ``CALLIO_OLLAMA_BASE_URL`` (or ``CALLIO_LLM_BASE_URL``) and sets
  ``api_key="ollama"``.
* ``openai`` — OpenAI hosted API. Reads ``OPENAI_API_KEY`` from env unless
  ``CALLIO_LLM_API_KEY`` is set explicitly.
* ``anthropic`` — Anthropic's OpenAI-compatible endpoint.
  Reads ``ANTHROPIC_API_KEY`` unless ``CALLIO_LLM_API_KEY`` is set.
* ``gemini`` — Google Gemini's OpenAI-compatible endpoint.
  Reads ``GEMINI_API_KEY`` (or ``GOOGLE_API_KEY``) unless
  ``CALLIO_LLM_API_KEY`` is set.
* ``deepseek`` — DeepSeek's OpenAI-compatible endpoint.
  Reads ``DEEPSEEK_API_KEY`` unless ``CALLIO_LLM_API_KEY`` is set.
* ``qwen`` — Alibaba Qwen via DashScope OpenAI-compatible endpoint.
  Reads ``DASHSCOPE_API_KEY`` unless ``CALLIO_LLM_API_KEY`` is set.
* ``kimi`` — Moonshot AI Kimi OpenAI-compatible endpoint.
  Reads ``MOONSHOT_API_KEY`` unless ``CALLIO_LLM_API_KEY`` is set.
* ``openai_compatible`` — any OpenAI-compatible third-party API
  (Groq, Together, Mistral, …).
  Requires ``CALLIO_LLM_BASE_URL`` and ``CALLIO_LLM_API_KEY``.
* ``deepseek`` / ``qwen`` / ``kimi`` — OpenAI-compatible cloud presets
    with built-in base URLs and provider-specific API key env fallbacks.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from callio.config.settings import Settings

# Well-known OpenAI-compatible base URLs for hosted providers
_PROVIDER_BASE_URLS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.cn/v1",
}

_OPENAI_COMPAT_CLOUD_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.cn/v1",
}

# Environment variable names that store the API key for each provider
_PROVIDER_KEY_ENVS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
}

# Fallback env vars tried when the primary one is absent
_PROVIDER_KEY_FALLBACKS: dict[str, str] = {
    "gemini": "GOOGLE_API_KEY",
}


def _resolve_api_key(provider: str, explicit: str) -> str:
    """Return the API key to use, checking explicit value then env vars."""
    if explicit:
        return explicit
    primary_env = _PROVIDER_KEY_ENVS.get(provider, "")
    key = os.getenv(primary_env, "")
    if not key:
        fallback_env = _PROVIDER_KEY_FALLBACKS.get(provider, "")
        if fallback_env:
            key = os.getenv(fallback_env, "")
    return key


def build_chat_client(settings: "Settings") -> AsyncOpenAI:
    """Return an ``AsyncOpenAI``-compatible client for the configured provider.

    Args:
        settings: Runtime settings instance.

    Returns:
        An ``AsyncOpenAI`` client wired to the appropriate base URL and
        API key.  All providers use the OpenAI-compatible interface so
        worker runners require no provider-specific branching.
    """
    provider = (settings.llm_provider or "ollama").strip().lower()
    explicit_key = (settings.llm_api_key or "").strip()
    explicit_base = (settings.llm_base_url or "").strip()

    if provider == "openai":
        # AsyncOpenAI reads OPENAI_API_KEY automatically when no key is
        # supplied, so we only pass an explicit key when one was configured.
        kwargs: dict[str, str] = {}
        if explicit_key:
            kwargs["api_key"] = explicit_key
        return AsyncOpenAI(**kwargs)

    if provider in _PROVIDER_BASE_URLS:
        # anthropic, gemini — expose OpenAI-compat endpoints
        api_key = _resolve_api_key(provider, explicit_key)
        base_url = explicit_base or _PROVIDER_BASE_URLS[provider]
        return AsyncOpenAI(base_url=base_url, api_key=api_key)

    if provider in _OPENAI_COMPAT_CLOUD_BASE_URLS:
        api_key = _resolve_api_key(provider, explicit_key)
        base_url = explicit_base or _OPENAI_COMPAT_CLOUD_BASE_URLS[provider]
        return AsyncOpenAI(base_url=base_url, api_key=api_key)

    if provider == "openai_compatible":
        if not explicit_base:
            raise ValueError(
                "CALLIO_LLM_BASE_URL must be set when CALLIO_LLM_PROVIDER=openai_compatible"
            )
        return AsyncOpenAI(base_url=explicit_base, api_key=explicit_key)

    # "ollama" or unrecognised → generic compat path
    base_url = explicit_base or settings.ollama_base_url
    api_key = explicit_key or ("ollama" if provider == "ollama" else "")
    return AsyncOpenAI(base_url=base_url, api_key=api_key)
