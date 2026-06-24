from __future__ import annotations

import asyncio
import logging
import sys
import threading
from typing import Any

from callio.config.settings import Settings
from callio.voice.whisper_loader import apply_hf_mirror

logger = logging.getLogger(__name__)

CHATT_SAMPLE_RATE = 24_000
_TRANSFORMERS_FIX = "pip install 'transformers>=4.41,<5'"

_chat: Any = None
_speaker: str | None = None
_lock = threading.Lock()
_preload_lock: asyncio.Lock | None = None
_ready = asyncio.Event()
_preload_error: str | None = None


def _get_preload_lock() -> asyncio.Lock:
    global _preload_lock
    if _preload_lock is None:
        _preload_lock = asyncio.Lock()
    return _preload_lock


def _print_tts_diagnostics(exc: Exception) -> None:
    try:
        import transformers

        tf_version = transformers.__version__
        tf_path = getattr(transformers, "__file__", "?")
    except Exception:
        tf_version = "not installed"
        tf_path = "?"

    print("\n--- TTS Diagnostics ---")
    print(f"Python: {sys.executable}")
    print(f"transformers: {tf_version} ({tf_path})")
    if "LlamaModel" in str(exc):
        print(f"Fix: {_TRANSFORMERS_FIX}")
        print("Make sure you are using the venv: ./venv/bin/python -m callio")
    elif "timed out" in str(exc).lower() or "github" in str(exc).lower():
        print("Fix: export CALLIO_HF_ENDPOINT=https://hf-mirror.com")
        print("First-time model download can be slow — please wait or retry later.")


def _ensure_transformers_compatible() -> None:
    try:
        import transformers
    except ImportError as exc:
        raise ImportError(
            f"transformers is not installed; run: {_TRANSFORMERS_FIX}"
        ) from exc

    version = transformers.__version__
    major = int(version.split(".", 1)[0])
    if major >= 5:
        raise ImportError(
            f"transformers {version} is incompatible with ChatTTS (missing LlamaModel); run: {_TRANSFORMERS_FIX}"
        )

    try:
        from transformers import LlamaConfig, LlamaModel  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            f"transformers {version} cannot import LlamaModel; run: {_TRANSFORMERS_FIX}"
        ) from exc


def _load_chatt_sync(settings: Settings) -> tuple[Any, str]:
    _ensure_transformers_compatible()
    import ChatTTS

    apply_hf_mirror(settings)

    custom_path = (settings.chatt_home or "").strip() or None
    logger.info("Loading ChatTTS model (first run downloads from HuggingFace)...")
    if settings.hf_endpoint:
        logger.info("Using HF mirror: %s", settings.hf_endpoint)

    chat = ChatTTS.Chat()
    if hasattr(chat, "load"):
        loaded = chat.load(compile=False, source="huggingface", custom_path=custom_path)
    else:
        loaded = chat.load_models(compile=False)

    if loaded is False:
        raise RuntimeError(
            "ChatTTS model failed to load. Set CALLIO_HF_ENDPOINT=https://hf-mirror.com and retry, or set CALLIO_CHATTTS_HOME to a local model directory."
        )

    speaker = chat.sample_random_speaker()
    logger.info("ChatTTS model ready")
    return chat, speaker


async def preload_tts(settings: Settings) -> None:
    global _chat, _speaker, _preload_error

    if settings.tts_backend != "chatt" or not settings.tts_preload:
        _ready.set()
        return

    async with _get_preload_lock():
        if _ready.is_set() and _chat is not None:
            return

        try:
            loaded_chat, loaded_speaker = await asyncio.to_thread(_load_chatt_sync, settings)
            with _lock:
                _chat = loaded_chat
                _speaker = loaded_speaker
                _preload_error = None
        except Exception as exc:
            _preload_error = str(exc)
            logger.exception("ChatTTS preload failed")
            _print_tts_diagnostics(exc)
            logger.warning("ChatTTS preload failed, falling back to macOS say: %s", exc)
        finally:
            _ready.set()


async def wait_for_tts(settings: Settings) -> None:
    if settings.tts_backend != "chatt":
        return
    if not _ready.is_set():
        await preload_tts(settings)
    await _ready.wait()


def is_chatt_ready() -> bool:
    return _chat is not None


def get_preload_error() -> str | None:
    return _preload_error


def get_chatt() -> tuple[Any, str] | None:
    with _lock:
        if _chat is None or _speaker is None:
            return None
        return _chat, _speaker


def synthesize_chatt(text: str, settings: Settings) -> bytes:
    global _chat, _speaker

    from callio.voice.audio_utils import float32_to_pcm_bytes

    import numpy as np

    loaded = get_chatt()
    if loaded is None:
        loaded = _load_chatt_sync(settings)
        with _lock:
            _chat, _speaker = loaded

    chat, speaker = loaded
    import ChatTTS

    params_infer_code = ChatTTS.Chat.InferCodeParams(
        spk_emb=speaker,
        temperature=0.3,
        top_P=0.7,
        top_K=20,
    )
    params_refine_text = ChatTTS.Chat.RefineTextParams(
        prompt="[oral_2][laugh_0][break_4]",
    )

    wavs = chat.infer(
        [text],
        params_refine_text=params_refine_text,
        params_infer_code=params_infer_code,
    )
    if not wavs:
        return b""

    samples = np.asarray(wavs[0], dtype=np.float32)
    return float32_to_pcm_bytes(
        samples,
        source_rate=CHATT_SAMPLE_RATE,
        target_rate=settings.audio_out_sample_rate,
    )
