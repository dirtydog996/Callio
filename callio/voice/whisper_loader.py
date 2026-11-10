from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

from callio.config.settings import Settings
from callio.voice.smart_turn_factory import estimate_stt_ttfs_p99

logger = logging.getLogger(__name__)


def _segment_passes_quality_checks(segment, settings: Settings) -> bool:
    avg_logprob = getattr(segment, "avg_logprob", None)
    if avg_logprob is not None and avg_logprob < settings.whisper_log_prob_threshold:
        return False
    ratio = getattr(segment, "compression_ratio", None)
    if ratio is not None and ratio > settings.whisper_compression_ratio_max:
        return False
    return True

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

    logger.info("Loading Whisper model: %s", settings.whisper_model)
    model = WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    logger.info("Whisper model ready: %s", settings.whisper_model)
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
            logger.warning("Whisper preload failed: %s", exc)
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
    from pipecat.transcriptions.language import Language
    from pipecat.utils.time import time_now_iso8601

    from callio.voice.segmented_stt import (
        CallioSegmentedSTTService,
        CallioWhisperSTTSettings,
        language_to_whisper_language,
    )

    def _assert_given(value, name: str = "value"):
        if value is None:
            raise ValueError(f"{name} is required")
        return value

    apply_hf_mirror(settings)

    class PreloadedWhisperSTTService(CallioSegmentedSTTService):
        def __init__(self, *, device: str, compute_type: str, **kwargs) -> None:
            self._device = device
            self._compute_type = compute_type
            super().__init__(**kwargs)
            self._load()

        def _load(self) -> None:
            key = _model_cache_key(settings)
            with _lock:
                if _model is not None and _model_key == key:
                    self._model = _model
                    logger.debug("Reusing preloaded Whisper model")
                    return
            from faster_whisper import WhisperModel

            model_name = settings.whisper_model
            logger.info("Loading Whisper model on demand: %s", model_name)
            self._model = WhisperModel(
                model_name,
                device=self._device,
                compute_type=self._compute_type,
            )

        async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
            if not self._model:
                yield ErrorFrame("Whisper model not available")
                return

            min_samples = int(
                settings.audio_in_sample_rate * settings.whisper_min_segment_ms / 1000
            )
            if len(audio) < min_samples * 2:
                logger.debug(
                    "Skipping short segment (%d ms)",
                    len(audio) // 2 * 1000 // settings.audio_in_sample_rate,
                )
                return

            await self.start_processing_metrics()
            text: str = ""
            exc: BaseException | None = None
            try:
                audio_float = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0

                language = _assert_given(self._settings.language, "language")
                whisper_lang = language_to_whisper_language(language) if language else None

                def _transcribe_sync():
                    prompt = (settings.whisper_initial_prompt or "").strip() or None
                    hotwords = (settings.whisper_hotwords or "").strip() or None
                    kwargs: dict = {
                        "language": whisper_lang,
                        "vad_filter": True,
                        "condition_on_previous_text": False,
                        "beam_size": max(1, settings.whisper_beam_size),
                        "compression_ratio_threshold": settings.whisper_compression_ratio_max,
                        "log_prob_threshold": settings.whisper_log_prob_threshold,
                        "temperature": 0.0,
                    }
                    if prompt:
                        kwargs["initial_prompt"] = prompt
                    if hotwords:
                        kwargs["hotwords"] = hotwords
                    segs, _ = self._model.transcribe(audio_float, **kwargs)
                    return list(segs)

                segments = await asyncio.to_thread(_transcribe_sync)

                no_speech_prob_threshold = _assert_given(
                    self._settings.no_speech_prob, "no_speech_prob"
                )
                for segment in segments:
                    if (
                        no_speech_prob_threshold is not None
                        and segment.no_speech_prob < no_speech_prob_threshold
                        and _segment_passes_quality_checks(segment, settings)
                    ):
                        text += f"{segment.text} "
            except Exception as e:
                exc = e
            finally:
                await self.stop_processing_metrics()

            if exc is not None:
                logger.error("Whisper transcription error: %s", exc)
                yield ErrorFrame(error=f"Whisper transcription error: {exc}")
                return

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
        ttfs_p99_latency=estimate_stt_ttfs_p99(settings),
        settings=CallioWhisperSTTSettings(
            model=settings.whisper_model,
            language=Language.ZH,
            no_speech_prob=0.6,
            hotwords=None,
            initial_prompt=settings.whisper_initial_prompt or None,
        ),
    )
