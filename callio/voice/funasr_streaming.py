from __future__ import annotations

import asyncio
import logging
import re
import threading
from typing import Any

import numpy as np

from callio.config.settings import Settings
from callio.voice.funasr_loader import _load_funasr_sync, _lock

logger = logging.getLogger(__name__)

_CHUNK_SIZE = [0, 10, 5]
_ENCODER_LOOK_BACK = 4
_DECODER_LOOK_BACK = 1


def _chunk_stride_samples(sample_rate: int = 16000) -> int:
    return _CHUNK_SIZE[1] * 960


def _clean_funasr_text(text: str) -> str:
    return re.sub(r"<\|[^|]+\|>", "", text or "").strip()


def _streaming_transcribe_sync(
    model: Any,
    audio_float: np.ndarray,
    *,
    cache: dict,
    is_final: bool,
) -> str:
    chunk_stride = _chunk_stride_samples()
    if len(audio_float) == 0:
        return ""
    tail = audio_float[-chunk_stride:] if len(audio_float) >= chunk_stride else audio_float
    if len(tail) < chunk_stride:
        tail = np.pad(tail, (chunk_stride - len(tail), 0))

    result = model.generate(
        input=tail.astype(np.float32),
        cache=cache,
        is_final=is_final,
        chunk_size=_CHUNK_SIZE,
        encoder_chunk_look_back=_ENCODER_LOOK_BACK,
        decoder_chunk_look_back=_DECODER_LOOK_BACK,
    )
    if not result:
        return ""
    return _clean_funasr_text(result[0].get("text", ""))


def create_streaming_sensevoice_stt(settings: Settings):
    """Streaming FunASR STT for SenseVoice / Paraformer-online backends."""
    from collections.abc import AsyncGenerator

    from pipecat.frames.frames import Frame, InterimTranscriptionFrame, TranscriptionFrame
    from pipecat.processors.frame_processor import FrameDirection
    from pipecat.services.settings import STTSettings
    from pipecat.services.stt_service import STTService
    from pipecat.transcriptions.language import Language
    from pipecat.utils.time import time_now_iso8601

    model_name = (settings.funasr_streaming_model or settings.funasr_model).strip()
    sample_rate = settings.audio_in_sample_rate
    stride_bytes = _chunk_stride_samples(sample_rate) * 2

    class StreamingFunASRSTService(STTService):
        def __init__(self) -> None:
            super().__init__(
                sample_rate=sample_rate,
                ttfs_p99_latency=2.5,
                settings=STTSettings(model=model_name, language=Language.ZH),
            )
            self._model: Any = None
            self._session_audio = bytearray()
            self._cache: dict = {}
            self._last_interim = ""
            self._stream_lock = threading.Lock()
            self._since_last_chunk = 0

        def _ensure_model(self) -> bool:
            if self._model is not None:
                return True
            try:
                self._model = _load_funasr_sync(model_name)
            except Exception as exc:
                logger.exception("FunASR streaming model load failed: %s", exc)
                return False
            return True

        def _reset_turn(self) -> None:
            self._session_audio.clear()
            self._cache = {}
            self._last_interim = ""
            self._since_last_chunk = 0

        async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
            yield None

        async def _emit_interim(self, text: str) -> None:
            if not text or text == self._last_interim:
                return
            self._last_interim = text
            await self.push_frame(
                InterimTranscriptionFrame(
                    text,
                    self._user_id,
                    time_now_iso8601(),
                    Language.ZH,
                )
            )

        async def _infer(self, *, is_final: bool) -> None:
            if not self._ensure_model():
                await self.push_error("FunASR streaming model not available")
                return
            pcm = bytes(self._session_audio)
            if not pcm:
                return
            audio_float = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

            def _work() -> tuple[str, str]:
                with self._stream_lock:
                    partial = _streaming_transcribe_sync(
                        self._model, audio_float, cache=self._cache, is_final=False
                    )
                    final = ""
                    if is_final:
                        final = _streaming_transcribe_sync(
                            self._model, audio_float, cache=self._cache, is_final=True
                        )
                return partial, final

            partial, final = await asyncio.to_thread(_work)
            if not is_final:
                await self._emit_interim(partial)
                return
            text = final or partial or self._last_interim
            if text:
                logger.info("FunASR streaming final: %s", text)
                await self.push_frame(
                    TranscriptionFrame(
                        text,
                        self._user_id,
                        time_now_iso8601(),
                        Language.ZH,
                        result={"streaming": True},
                    )
                )
                await self.emit_stt_usage_metrics()

        async def _handle_vad_user_started_speaking(self, frame):
            await super()._handle_vad_user_started_speaking(frame)
            self._reset_turn()

        async def _handle_vad_user_stopped_speaking(self, frame):
            await self._infer(is_final=True)
            await super()._handle_vad_user_stopped_speaking(frame)

        async def process_audio_frame(self, frame, direction: FrameDirection):
            if self._reconnecting or self._muted or not self.is_usable:
                return
            if not frame.audio:
                return
            if not self._user_speaking:
                if self._audio_passthrough:
                    await self.push_frame(frame, direction)
                return

            self._session_audio.extend(frame.audio)
            self._since_last_chunk += len(frame.audio)
            self._record_stt_audio_usage(frame.audio)

            if self._since_last_chunk >= stride_bytes:
                self._since_last_chunk = 0
                await self._infer(is_final=False)

            if self._audio_passthrough:
                await self.push_frame(frame, direction)

    return StreamingFunASRSTService()
