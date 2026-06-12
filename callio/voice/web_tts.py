from __future__ import annotations

import asyncio
import io
import logging
import subprocess
import tempfile
import wave
from collections.abc import AsyncGenerator
from pathlib import Path

import numpy as np
from pipecat.frames.frames import Frame, OutputAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language

logger = logging.getLogger(__name__)

_chinese_voice: str | None = None
_CHUNK_MS = 20


def _detect_chinese_voice() -> str:
    global _chinese_voice
    if _chinese_voice is not None:
        return _chinese_voice

    try:
        result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        _chinese_voice = ""
        return _chinese_voice

    for line in result.stdout.splitlines():
        for marker in ("zh_CN", "zh_TW"):
            if marker in line:
                _chinese_voice = line.split(marker, 1)[0].strip()
                return _chinese_voice

    _chinese_voice = ""
    return _chinese_voice


def synthesize_wav(text: str, voice: str = "") -> bytes:
    with tempfile.TemporaryDirectory() as tmp_dir:
        aiff_path = Path(tmp_dir) / "speech.aiff"
        wav_path = Path(tmp_dir) / "speech.wav"
        say_cmd = ["say", "-o", str(aiff_path), text]
        if voice:
            say_cmd = ["say", "-v", voice, "-o", str(aiff_path), text]

        subprocess.run(say_cmd, check=True, capture_output=True)
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16", str(aiff_path), str(wav_path)],
            check=True,
            capture_output=True,
        )
        return wav_path.read_bytes()


def wav_to_pcm_bytes(wav_bytes: bytes, target_rate: int) -> bytes:
    with io.BytesIO(wav_bytes) as buffer:
        with wave.open(buffer, "rb") as wf:
            channels = wf.getnchannels()
            source_rate = wf.getframerate()
            pcm = wf.readframes(wf.getnframes())

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if len(samples) == 0:
        return b""

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

    if source_rate != target_rate:
        ratio = source_rate / target_rate
        out_len = max(1, int(len(samples) / ratio))
        resampled = np.zeros(out_len, dtype=np.float32)
        for i in range(out_len):
            pos = i * ratio
            idx = int(pos)
            frac = pos - idx
            a = samples[min(idx, len(samples) - 1)]
            b = samples[min(idx + 1, len(samples) - 1)]
            resampled[i] = a + (b - a) * frac
        samples = resampled

    return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def iter_pcm_chunks(pcm: bytes, sample_rate: int, *, chunk_ms: int = _CHUNK_MS) -> list[bytes]:
    bytes_per_chunk = int(sample_rate * (chunk_ms / 1000.0) * 2)
    bytes_per_chunk = max(bytes_per_chunk, 2)
    return [pcm[i : i + bytes_per_chunk] for i in range(0, len(pcm), bytes_per_chunk) if pcm[i : i + bytes_per_chunk]]


def create_web_audio_tts(*, sample_rate: int = 16000) -> TTSService:
    voice = _detect_chinese_voice()

    class MacWebAudioTTSService(TTSService):
        def __init__(self) -> None:
            super().__init__(
                push_stop_frames=True,
                sample_rate=sample_rate,
                settings=TTSSettings(model=None, voice=voice or None, language=Language.ZH),
            )
            self._voice = voice

        async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
            if not text.strip():
                yield None
                return

            try:
                wav_bytes = await asyncio.to_thread(synthesize_wav, text, self._voice)
                pcm = wav_to_pcm_bytes(wav_bytes, sample_rate)
                if not pcm:
                    yield None
                    return
                for chunk in iter_pcm_chunks(pcm, sample_rate):
                    yield OutputAudioRawFrame(
                        audio=chunk,
                        sample_rate=sample_rate,
                        num_channels=1,
                    )
                logger.info("Streamed assistant audio (%d bytes PCM)", len(pcm))
            except Exception as exc:
                logger.warning("Mac web TTS failed: %s", exc)
            yield None

    return MacWebAudioTTSService()
