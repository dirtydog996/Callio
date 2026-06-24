"""SenseVoice / FunASR STT backend.

Install:
  pip install funasr modelscope huggingface_hub

First run downloads the model to ~/.cache/modelscope/ (≈300 MB for SenseVoiceSmall).

Usage:  CALLIO_STT_BACKEND=sensevoice  CALLIO_FUNASR_MODEL=iic/SenseVoiceSmall

Supported models:
  iic/SenseVoiceSmall    – fast, accurate Chinese + multilingual (recommended)
  iic/paraformer-zh      – Paraformer-zh, Chinese only, very accurate
  iic/paraformer-zh-streaming – streaming Paraformer
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import numpy as np

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


def _load_funasr_sync(model_name: str) -> Any:
    from funasr import AutoModel  # noqa: PLC0415

    logger.info("Loading FunASR model: %s", model_name)
    model = AutoModel(
        model=model_name,
        trust_remote_code=True,
        disable_update=True,
    )
    logger.info("FunASR model ready: %s", model_name)
    return model


async def preload_funasr(settings: Settings) -> None:
    global _model, _model_key, _preload_error

    if settings.stt_backend != "sensevoice":
        _ready.set()
        return

    async with _get_preload_lock():
        if _ready.is_set():
            return
        model_name = settings.funasr_model or "iic/SenseVoiceSmall"
        with _lock:
            if _model is not None and _model_key == model_name:
                _ready.set()
                return
        try:
            loaded = await asyncio.to_thread(_load_funasr_sync, model_name)
            with _lock:
                _model = loaded
                _model_key = model_name
                _preload_error = None
        except Exception as exc:
            _preload_error = str(exc)
            logger.exception("FunASR preload failed")
            logger.warning("FunASR preload failed: %s", exc)
        finally:
            _ready.set()


async def wait_for_funasr(settings: Settings) -> None:
    if not _ready.is_set():
        await preload_funasr(settings)
    await _ready.wait()


def is_funasr_ready() -> bool:
    return _model is not None


def get_preload_error() -> str | None:
    return _preload_error


def _transcribe_sync(model: Any, audio_int16: bytes, sample_rate: int) -> str:
    """Run FunASR/SenseVoice inference; returns transcribed text."""
    audio_float = np.frombuffer(audio_int16, dtype=np.int16).astype(np.float32) / 32768.0

    result = model.generate(
        input=audio_float,
        input_len=np.array([len(audio_float)]),
        language="auto",
        use_itn=True,
        ban_emo_unk=True,
    )
    if not result:
        return ""
    text = result[0].get("text", "")
    # SenseVoice output may contain emotion/event tags like <|HAPPY|>; strip them
    import re
    text = re.sub(r"<\|[^|]+\|>", "", text).strip()
    return text


def create_sensevoice_stt(settings: Settings):
    """Return a Pipecat-compatible SenseVoice STT service."""
    from collections.abc import AsyncGenerator

    from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
    from pipecat.services.settings import assert_given
    from pipecat.services.whisper.stt import (
        WhisperSTTService,
        WhisperSTTSettings,
        language_to_whisper_language,
    )
    from pipecat.transcriptions.language import Language
    from pipecat.utils.time import time_now_iso8601

    model_name = settings.funasr_model or "iic/SenseVoiceSmall"

    class SenseVoiceSTTService(WhisperSTTService):
        """Replaces Whisper inference with FunASR/SenseVoice while keeping
        the pipecat VAD + buffering pipeline intact."""

        def _load(self) -> None:
            global _model, _model_key
            with _lock:
                if _model is not None and _model_key == model_name:
                    self._model = _model
                    logger.debug("Reusing preloaded FunASR model")
                    return
            # If not preloaded yet, load now (blocks; called in thread)
            loaded = _load_funasr_sync(model_name)
            with _lock:
                _model = loaded
                _model_key = model_name
            self._model = loaded

        async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
            if not self._model:
                yield ErrorFrame("FunASR model not available")
                return

            await self.start_processing_metrics()
            try:
                text = await asyncio.to_thread(
                    _transcribe_sync, self._model, audio,
                    settings.audio_in_sample_rate,
                )
            except Exception as exc:
                logger.warning("SenseVoice transcription error: %s", exc)
                await self.stop_processing_metrics()
                return

            await self.stop_processing_metrics()
            if text:
                logger.info("SenseVoice transcription: %s", text)
                language = assert_given(self._settings.language)
                await self._handle_transcription(text, True, language)
                yield TranscriptionFrame(
                    text,
                    self._user_id,
                    time_now_iso8601(),
                    language,
                )

    return SenseVoiceSTTService(
        device="cpu",
        compute_type="default",
        ttfs_p99_latency=3.0,
        settings=WhisperSTTSettings(
            model=model_name,
            language=Language.ZH,
            no_speech_prob=0.6,
        ),
    )
