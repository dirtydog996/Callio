"""CosyVoice TTS backend – connects to a running CosyVoice REST API server.

Start the server:
  git clone https://github.com/FunAudioLLM/CosyVoice
  cd CosyVoice && pip install -r requirements.txt
  python runtime/python/fastapi/server.py --port 9880

Usage:  CALLIO_TTS_BACKEND=cosyvoice  CALLIO_COSYVOICE_URL=http://localhost:9880

API endpoint used:  POST /inference_sft
  Body (JSON):  {"tts_text": "...", "spk_id": "<CosyVoice speaker id>"}
  Response:     audio/wav bytes (streamed)
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


def _cosyvoice_synthesize(base_url: str, text: str, spk_id: str, target_rate: int) -> bytes:
    url = base_url.rstrip("/") + "/inference_sft"
    resp = requests.post(
        url,
        json={"tts_text": text, "spk_id": spk_id},
        timeout=60,
    )
    resp.raise_for_status()
    return wav_to_pcm_bytes(resp.content, target_rate)


def create_cosyvoice_tts(settings: Settings, *, sample_rate: int) -> TTSService:
    """Return a Pipecat-compatible CosyVoice TTS service (HTTP-API mode)."""
    base_url = settings.cosyvoice_base_url or "http://localhost:9880"
    # CosyVoice speaker ID — override via CALLIO_COSYVOICE_URL or custom API
    spk_id = "中文女"

    class CosyVoiceTTSService(TTSService):
        def __init__(self) -> None:
            super().__init__(
                push_stop_frames=True,
                sample_rate=sample_rate,
                settings=TTSSettings(model="cosyvoice", voice=spk_id, language=Language.ZH),
            )
            self._base_url = base_url
            self._spk_id = spk_id
            self._sample_rate = sample_rate

        async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
            if not text.strip():
                yield None
                return
            try:
                pcm = await asyncio.to_thread(
                    _cosyvoice_synthesize,
                    self._base_url,
                    text,
                    self._spk_id,
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
                logger.info("Streamed assistant audio via CosyVoice (%d bytes PCM)", len(pcm))
            except requests.exceptions.ConnectionError:
                logger.error(
                    "Cannot connect to CosyVoice server %s — please start the server first", self._base_url
                )
            except Exception as exc:
                logger.warning("CosyVoice TTS failed: %s", exc)
            yield None

    return CosyVoiceTTSService()
