from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from callio.web import APP_DIR, MOBILE_DIR, SHARED_DIR, STATIC_DIR

BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class Settings:
    app_title: str = "Callio API Gateway"
    app_version: str = "1.0"
    db_path: str = str(BASE_DIR / "callio_local.db")
    app_dir: str = os.getenv("CALLIO_APP_DIR", str(APP_DIR))
    static_dir: str = os.getenv("CALLIO_STATIC_DIR", str(STATIC_DIR))
    mobile_dir: str = os.getenv("CALLIO_MOBILE_DIR", str(MOBILE_DIR))
    shared_dir: str = os.getenv("CALLIO_SHARED_DIR", str(SHARED_DIR))
    session_token_limit: int = 10
    voice_response_limit: int = 30
    llm_model: str = os.getenv("CALLIO_LLM_MODEL", "qwen2.5:7b")
    # LLM provider: ollama (default) | openai | anthropic | gemini | openai_compatible
    llm_provider: str = os.getenv("CALLIO_LLM_PROVIDER", "ollama")
    # Generic API key for the selected LLM provider (e.g. OPENAI_API_KEY for openai).
    # Falls back to provider-specific env vars (OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY).
    llm_api_key: str = os.getenv("CALLIO_LLM_API_KEY", "")
    # Generic LLM base URL override; takes precedence over ollama_base_url for non-ollama providers.
    llm_base_url: str = os.getenv("CALLIO_LLM_BASE_URL", "")
    # Kept for backward compatibility; used as default base URL when llm_provider=ollama.
    ollama_base_url: str = os.getenv("CALLIO_OLLAMA_BASE_URL", "http://localhost:11434/v1")
    whisper_model: str = os.getenv("CALLIO_WHISPER_MODEL", "base")
    whisper_device: str = os.getenv("CALLIO_WHISPER_DEVICE", "cpu")
    whisper_compute_type: str = os.getenv("CALLIO_WHISPER_COMPUTE_TYPE", "default")
    whisper_preload: bool = os.getenv("CALLIO_WHISPER_PRELOAD", "1") == "1"
    tts_backend: str = os.getenv("CALLIO_TTS_BACKEND", "chatt")
    tts_preload: bool = os.getenv("CALLIO_TTS_PRELOAD", "1") == "1"
    chatt_home: str = os.getenv("CALLIO_CHATTTS_HOME", "")
    audio_out_sample_rate: int = int(os.getenv("CALLIO_AUDIO_OUT_SAMPLE_RATE", "16000"))
    hf_endpoint: str = os.getenv("CALLIO_HF_ENDPOINT", os.getenv("HF_ENDPOINT", ""))
    host: str = os.getenv("CALLIO_HOST", "0.0.0.0")
    port: int = int(os.getenv("CALLIO_PORT", "8000"))
    ssl_certfile: str = os.getenv("CALLIO_SSL_CERT", "")
    ssl_keyfile: str = os.getenv("CALLIO_SSL_KEY", "")
    audio_in_sample_rate: int = 16000
    sandbox_root: str = os.getenv("CALLIO_SANDBOX_ROOT", str(BASE_DIR))
    shadow_root: str = os.getenv("CALLIO_SHADOW_ROOT", str(BASE_DIR / ".callio_shadow"))
    sandbox_use_docker: bool = os.getenv("CALLIO_USE_DOCKER", "0") == "1"
    enable_git_resets: bool = os.getenv("CALLIO_ENABLE_GIT_RESETS", "0") == "1"
    watchdog_health_path: str = "/api/v1/health"
    max_parallel_tasks: int = int(os.getenv("CALLIO_MAX_PARALLEL_TASKS", "3"))
    summarize_debounce_sec: int = int(os.getenv("CALLIO_SUMMARIZE_DEBOUNCE_SEC", "30"))
    progress_inject: bool = os.getenv("CALLIO_PROGRESS_INJECT", "1") == "1"
    memory_inject: bool = os.getenv("CALLIO_MEMORY_INJECT", "1") == "1"
    require_verbal_confirm: bool = os.getenv("CALLIO_REQUIRE_VERBAL_CONFIRM", "1") == "1"
    agent_backend: str = os.getenv("CALLIO_AGENT_BACKEND", "")
    agent_command: str = os.getenv("CALLIO_AGENT_COMMAND", "")
    task_timeout_sec: int = int(os.getenv("CALLIO_TASK_TIMEOUT_SEC", "3600"))
    global_max_parallel: int = int(os.getenv("CALLIO_GLOBAL_MAX_PARALLEL", "5"))
    execute_max_retries: int = int(os.getenv("CALLIO_EXECUTE_MAX_RETRIES", "3"))
    # VAD: seconds of silence after user stops speaking before sending to STT
    vad_stop_secs: float = float(os.getenv("CALLIO_VAD_STOP_SECS", "0.4"))
    # STT backend: whisper (default) | sensevoice
    stt_backend: str = os.getenv("CALLIO_STT_BACKEND", "whisper")
    # FunASR / SenseVoice model name (used when stt_backend=sensevoice)
    funasr_model: str = os.getenv("CALLIO_FUNASR_MODEL", "iic/SenseVoiceSmall")
    # EdgeTTS voice name (used when tts_backend=edge)
    edge_tts_voice: str = os.getenv("CALLIO_EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
    # CosyVoice REST API base URL (used when tts_backend=cosyvoice)
    cosyvoice_base_url: str = os.getenv("CALLIO_COSYVOICE_URL", "http://localhost:9880")
    # Fish Speech REST API base URL (used when tts_backend=fish)
    fish_speech_url: str = os.getenv("CALLIO_FISH_SPEECH_URL", "http://localhost:8080")
    # Generic notification webhooks (triggered when a voice session ends)
    notify_wechat_webhook: str = os.getenv("CALLIO_NOTIFY_WECHAT_WEBHOOK", "")
    notify_feishu_webhook: str = os.getenv("CALLIO_NOTIFY_FEISHU_WEBHOOK", "")
    notify_discord_webhook: str = os.getenv("CALLIO_NOTIFY_DISCORD_WEBHOOK", "")
    notify_telegram_webhook: str = os.getenv("CALLIO_NOTIFY_TELEGRAM_WEBHOOK", "")
    notify_timeout_sec: int = int(os.getenv("CALLIO_NOTIFY_TIMEOUT_SEC", "8"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
