from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from callio.web import STATIC_DIR

BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class Settings:
    app_title: str = "Callio API Gateway"
    app_version: str = "1.0"
    db_path: str = str(BASE_DIR / "callio_local.db")
    static_dir: str = os.getenv("CALLIO_STATIC_DIR", str(STATIC_DIR))
    session_token_limit: int = 10
    voice_response_limit: int = 30
    llm_model: str = os.getenv("CALLIO_LLM_MODEL", "qwen2.5:7b")
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
