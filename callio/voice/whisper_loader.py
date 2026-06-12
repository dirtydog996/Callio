from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

from callio.config.settings import Settings

logger = logging.getLogger(__name__)

_model: Any = None
_model_key: str | None = None
_lock = threading.Lock()
_preload_lock: asyncio.Lock | None = None
_ready = asyncio.Event()
_preload_error: str | None = None


def _get_preload_lock() -> asyncio.Lock:
    global _preload_lock
    if _preload_lock is None:
        _preload_lock = asyncio.Lock()
    return _preload_lock


def apply_hf_mirror(settings: Settings) -> None:
    endpoint = (settings.hf_endpoint or "").strip().rstrip("/")
    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint
        logger.info("Using Hugging Face mirror: %s", endpoint)


def _model_cache_key(settings: Settings) -> str:
    return f"{settings.whisper_model}:{settings.whisper_device}:{settings.whisper_compute_type}"


def _load_model_sync(settings: Settings) -> Any:
    from faster_whisper import WhisperModel

    print(f"\n⏳ 正在加载 Whisper 模型 ({settings.whisper_model})...")
    model = WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    print(f"✅ Whisper 模型已就绪: {settings.whisper_model}")
    return model


async def preload_whisper(settings: Settings) -> None:
    global _model, _model_key, _preload_error

    if not settings.whisper_preload:
        _ready.set()
        return

    async with _get_preload_lock():
        if _ready.is_set():
            return

        apply_hf_mirror(settings)
        key = _model_cache_key(settings)

        with _lock:
            if _model is not None and _model_key == key:
                _ready.set()
                return

        try:
            loaded = await asyncio.to_thread(_load_model_sync, settings)
            with _lock:
                _model = loaded
                _model_key = key
                _preload_error = None
        except Exception as exc:
            _preload_error = str(exc)
            logger.exception("Whisper preload failed")
            print(f"\n❌ Whisper 模型预加载失败: {exc}")
        finally:
            _ready.set()


async def wait_for_whisper(settings: Settings) -> None:
    if not _ready.is_set():
        await preload_whisper(settings)
    await _ready.wait()


def is_whisper_ready() -> bool:
    return _model is not None


def get_preload_error() -> str | None:
    return _preload_error


def create_whisper_stt(settings: Settings):
    from collections.abc import AsyncGenerator

    import numpy as np
    from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
    from pipecat.services.settings import assert_given
    from pipecat.services.whisper.stt import (
        WhisperSTTService,
        WhisperSTTSettings,
        language_to_whisper_language,
    )
    from pipecat.transcriptions.language import Language
    from pipecat.utils.time import time_now_iso8601

    apply_hf_mirror(settings)

    class PreloadedWhisperSTTService(WhisperSTTService):
        def _load(self) -> None:
            key = _model_cache_key(settings)
            with _lock:
                if _model is not None and _model_key == key:
                    self._model = _model
                    logger.debug("Reusing preloaded Whisper model")
                    return
            super()._load()

        async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
            if not self._model:
                yield ErrorFrame("Whisper model not available")
                return

            await self.start_processing_metrics()
            audio_float = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0

            language = assert_given(self._settings.language)
            whisper_lang = language_to_whisper_language(language) if language else None
            segments, _ = await asyncio.to_thread(
                self._model.transcribe,
                audio_float,
                language=whisper_lang,
            )

            text = ""
            no_speech_prob_threshold = assert_given(self._settings.no_speech_prob)
            for segment in segments:
                if (
                    no_speech_prob_threshold is not None
                    and segment.no_speech_prob < no_speech_prob_threshold
                ):
                    text += f"{segment.text} "

            await self.stop_processing_metrics()

            if text.strip():
                logger.info("Whisper transcription: %s", text.strip())
                await self._handle_transcription(text, True, language)
                yield TranscriptionFrame(
                    text.strip(),
                    self._user_id,
                    time_now_iso8601(),
                    language,
                )

    return PreloadedWhisperSTTService(
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        ttfs_p99_latency=2.0,
        settings=WhisperSTTSettings(
            model=settings.whisper_model,
            language=Language.ZH,
            no_speech_prob=0.6,
        ),
    )
