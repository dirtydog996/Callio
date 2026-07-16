"""Pipecat LLM service factory for the real-time voice pipeline.

Builds the appropriate pipecat ``LLMService`` subclass based on
``settings.llm_provider``.  The returned object is compatible with the
pipecat ``Pipeline`` and supports ``register_function`` for tool calling.

Provider routing
----------------
* ``ollama``  (default) — ``OLLamaLLMService`` (pipecat built-in).
* ``openai`` — ``OpenAILLMService``.
* ``openai_compatible`` — ``OpenAILLMService`` with a custom ``base_url``.
  Requires ``CALLIO_LLM_BASE_URL`` and ``CALLIO_LLM_API_KEY``.
* ``anthropic`` — ``AnthropicLLMService``.
* ``gemini`` — ``GoogleLLMService`` (tries several pipecat import paths).

Import errors for optional providers propagate to the caller so that
the voice pipeline's existing ``except Exception`` fallback can handle them.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callio.config.settings import Settings

_PROVIDER_KEY_ENVS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

_PROVIDER_KEY_FALLBACKS: dict[str, str] = {
    "gemini": "GOOGLE_API_KEY",
}


def _resolve_api_key(provider: str, explicit: str) -> str:
    if explicit:
        return explicit
    primary_env = _PROVIDER_KEY_ENVS.get(provider, "")
    key = os.getenv(primary_env, "")
    if not key:
        fallback_env = _PROVIDER_KEY_FALLBACKS.get(provider, "")
        if fallback_env:
            key = os.getenv(fallback_env, "")
    return key


def build_voice_llm_service(settings: "Settings"):
    """Return the appropriate pipecat LLM service for the configured provider.

    Args:
        settings: Runtime settings instance.

    Returns:
        A pipecat LLM service instance ready for use in a ``Pipeline``.

    Raises:
        ImportError: If the required pipecat service for the selected
            provider is not installed.
        ValueError: If a required configuration (e.g. ``llm_base_url``)
            is missing for the selected provider.
    """
    provider = (settings.llm_provider or "ollama").strip().lower()
    model = settings.llm_model
    explicit_key = (settings.llm_api_key or "").strip()
    explicit_base = (settings.llm_base_url or "").strip()

    if provider == "openai":
        from pipecat.services.openai.llm import OpenAILLMService

        api_key = _resolve_api_key("openai", explicit_key)
        return OpenAILLMService(api_key=api_key, model=model)

    if provider == "openai_compatible":
        from pipecat.services.openai.llm import OpenAILLMService

        if not explicit_base:
            raise ValueError(
                "CALLIO_LLM_BASE_URL must be set when CALLIO_LLM_PROVIDER=openai_compatible"
            )
        return OpenAILLMService(base_url=explicit_base, api_key=explicit_key, model=model)

    if provider == "anthropic":
        from pipecat.services.anthropic.llm import AnthropicLLMService

        api_key = _resolve_api_key("anthropic", explicit_key)
        return AnthropicLLMService(api_key=api_key, model=model)

    if provider == "gemini":
        # pipecat exposes Gemini under different paths across versions; try both.
        try:
            from pipecat.services.google.llm import GoogleLLMService as _GeminiService
        except ImportError:
            from pipecat.services.google.gemini import GeminiLLMService as _GeminiService  # type: ignore[no-redef]

        api_key = _resolve_api_key("gemini", explicit_key)
        return _GeminiService(api_key=api_key, model=model)

    # Default: ollama (and any unrecognised provider)
    from pipecat.services.ollama.llm import OLLamaLLMService, OllamaLLMSettings

    base_url = explicit_base or settings.ollama_base_url
    return OLLamaLLMService(
        base_url=base_url,
        settings=OllamaLLMSettings(model=model),
    )
