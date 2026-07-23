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
* ``deepseek`` / ``qwen`` / ``kimi`` — ``OpenAILLMService`` with cloud
    OpenAI-compatible preset base URLs.
* ``anthropic`` — ``AnthropicLLMService``.
* ``gemini`` — ``GoogleLLMService`` (tries several pipecat import paths).

Import errors for optional providers propagate to the caller so that
the voice pipeline's existing ``except Exception`` fallback can handle them.
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING
from urllib.request import urlopen

if TYPE_CHECKING:
    from callio.config.settings import Settings

logger = logging.getLogger(__name__)

_PROVIDER_KEY_ENVS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

_PROVIDER_KEY_FALLBACKS: dict[str, str] = {
    "gemini": "GOOGLE_API_KEY",
}

_OPENAI_COMPAT_CLOUD_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.cn/v1",
}

_OPENAI_COMPAT_CLOUD_KEY_ENVS: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
}


def _ollama_tags_url(base_url: str) -> str:
    normalized = (base_url or "http://localhost:11434/v1").strip().rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return f"{normalized}/api/tags"


def _fetch_ollama_models(base_url: str) -> tuple[list[str], str | None]:
    url = _ollama_tags_url(base_url)
    try:
        with urlopen(url, timeout=2.5) as response:  # nosec B310 - runtime-configured local/service URL
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return [], str(exc)
    models = payload.get("models", []) if isinstance(payload, dict) else []
    names = sorted({str(item.get("name", "")).strip() for item in models if isinstance(item, dict) and item.get("name")})
    return names, None


def _resolve_ollama_model(base_url: str, configured_model: str) -> str:
    configured = (configured_model or "").strip()
    models, error = _fetch_ollama_models(base_url)
    if not models:
        if error:
            logger.warning("Could not validate Ollama model '%s' at %s: %s", configured, base_url, error)
        return configured
    if configured in models:
        return configured

    fallback = models[0]
    logger.warning(
        "Configured Ollama model '%s' was not found at %s. Falling back to installed model '%s'.",
        configured,
        base_url,
        fallback,
    )
    return fallback


def _resolve_api_key(provider: str, explicit: str) -> str:
    if explicit:
        return explicit
    if provider in _OPENAI_COMPAT_CLOUD_KEY_ENVS:
        return os.getenv(_OPENAI_COMPAT_CLOUD_KEY_ENVS[provider], "")
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

    if provider in _OPENAI_COMPAT_CLOUD_BASE_URLS:
        from pipecat.services.openai.llm import OpenAILLMService

        api_key = _resolve_api_key(provider, explicit_key)
        base_url = explicit_base or _OPENAI_COMPAT_CLOUD_BASE_URLS[provider]
        return OpenAILLMService(base_url=base_url, api_key=api_key, model=model)

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
    model = _resolve_ollama_model(base_url, model)
    return OLLamaLLMService(
        base_url=base_url,
        settings=OllamaLLMSettings(model=model),
    )
