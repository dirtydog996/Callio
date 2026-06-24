"""Fish Speech TTS backend – connects to a running Fish Speech inference server.

Start the server:
  pip install fish-speech
  python -m tools.api_server --listen 0.0.0.0:8080 --llama-checkpoint-path checkpoints/fish-speech-1.5

Usage:  CALLIO_TTS_BACKEND=fish  CALLIO_FISH_SPEECH_URL=http://localhost:8080

API endpoint used:  POST /v1/tts
  Body (JSON):  {"text": "...", "chunk_length": 200, "format": "wav"}
  Response:     audio/wav bytes
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

import requests

from pipecat.frames.frames import Frame, OutputAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language

from callio.config.settings import Settings
from callio.voice.audio_utils import iter_pcm_chunks, wav_to_pcm_bytes

logger = logging.getLogger(__name__)


def _fish_synthesize(base_url: str, text: str, target_rate: int) -> bytes:
    url = base_url.rstrip("/") + "/v1/tts"
    resp = requests.post(
        url,
        json={"text": text, "chunk_length": 200, "format": "wav"},
        timeout=60,
    )
    resp.raise_for_status()
    return wav_to_pcm_bytes(resp.content, target_rate)


def create_fish_tts(settings: Settings, *, sample_rate: int) -> TTSService:
    """Return a Pipecat-compatible Fish Speech TTS service (HTTP-API mode)."""
    base_url = settings.fish_speech_url or "http://localhost:8080"

    class FishTTSService(TTSService):
        def __init__(self) -> None:
            super().__init__(
                push_stop_frames=True,
                sample_rate=sample_rate,
                settings=TTSSettings(model="fish-speech", voice=None, language=Language.ZH),
            )
            self._base_url = base_url
            self._sample_rate = sample_rate

        async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
            if not text.strip():
                yield None
                return
            try:
                pcm = await asyncio.to_thread(
                    _fish_synthesize,
                    self._base_url,
                    text,
                    self._sample_rate,
                )
                if not pcm:
                    yield None
                    return
                for chunk in iter_pcm_chunks(pcm, self._sample_rate):
                    yield OutputAudioRawFrame(
                        audio=chunk,
                        sample_rate=self._sample_rate,
                        num_channels=1,
                    )
                logger.info("Streamed assistant audio via Fish Speech (%d bytes PCM)", len(pcm))
            except requests.exceptions.ConnectionError:
                logger.error(
                    "无法连接 Fish Speech 服务器 %s，请先启动服务器", self._base_url
                )
            except Exception as exc:
                logger.warning("Fish Speech TTS failed: %s", exc)
            yield None

    return FishTTSService()
