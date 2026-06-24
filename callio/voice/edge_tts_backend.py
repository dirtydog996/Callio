"""EdgeTTS backend – wraps Microsoft Edge TTS via the `edge-tts` package.

Install:  pip install edge-tts
Requires: ffmpeg on PATH for MP3 → PCM conversion.

Usage:  CALLIO_TTS_BACKEND=edge  CALLIO_EDGE_TTS_VOICE=zh-CN-XiaoxiaoNeural
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

from pipecat.frames.frames import Frame, OutputAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language

from callio.config.settings import Settings
from callio.voice.audio_utils import iter_pcm_chunks, wav_to_pcm_bytes

logger = logging.getLogger(__name__)


def _mp3_bytes_to_pcm(mp3_bytes: bytes, target_rate: int) -> bytes:
    """Convert raw MP3 bytes to 16-bit mono PCM at *target_rate* Hz via ffmpeg."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "EdgeTTS 需要 ffmpeg 进行 MP3→PCM 转换，请安装 ffmpeg：\n"
            "  macOS: brew install ffmpeg\n"
            "  Ubuntu: apt install ffmpeg"
        )
    with tempfile.TemporaryDirectory() as tmp:
        mp3_path = Path(tmp) / "speech.mp3"
        wav_path = Path(tmp) / "speech.wav"
        mp3_path.write_bytes(mp3_bytes)
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(mp3_path),
                "-ar", str(target_rate), "-ac", "1",
                "-f", "wav", str(wav_path),
            ],
            check=True,
            capture_output=True,
        )
        return wav_to_pcm_bytes(wav_path.read_bytes(), target_rate)


def create_edge_tts(settings: Settings, *, sample_rate: int) -> TTSService:
    """Return a Pipecat-compatible EdgeTTS service."""
    voice = settings.edge_tts_voice or "zh-CN-XiaoxiaoNeural"

    class EdgeTTSService(TTSService):
        def __init__(self) -> None:
            super().__init__(
                push_stop_frames=True,
                sample_rate=sample_rate,
                settings=TTSSettings(model="edge-tts", voice=voice, language=Language.ZH),
            )
            self._voice = voice
            self._sample_rate = sample_rate

        async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
            if not text.strip():
                yield None
                return
            try:
                import edge_tts  # noqa: PLC0415
            except ImportError:
                logger.error("edge-tts 未安装，请执行: pip install edge-tts")
                yield None
                return

            try:
                communicate = edge_tts.Communicate(text, self._voice)
                mp3_chunks: list[bytes] = []
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        mp3_chunks.append(chunk["data"])

                if not mp3_chunks:
                    yield None
                    return

                mp3_bytes = b"".join(mp3_chunks)
                pcm = await asyncio.to_thread(_mp3_bytes_to_pcm, mp3_bytes, self._sample_rate)
                if not pcm:
                    yield None
                    return

                for chunk in iter_pcm_chunks(pcm, self._sample_rate):
                    yield OutputAudioRawFrame(
                        audio=chunk,
                        sample_rate=self._sample_rate,
                        num_channels=1,
                    )
                logger.info("Streamed assistant audio via EdgeTTS (%d bytes PCM)", len(pcm))
            except Exception as exc:
                logger.warning("EdgeTTS failed: %s", exc)
            yield None

    return EdgeTTSService()
