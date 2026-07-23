from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

from pipecat.frames.frames import Frame, OutputAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language

from callio.config.settings import Settings, get_settings
from callio.voice.audio_utils import iter_pcm_chunks, wav_to_pcm_bytes

logger = logging.getLogger(__name__)

_chinese_voice: str | None = None


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


def synthesize_say_wav(text: str, voice: str = "") -> bytes:
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


_KNOWN_BACKENDS = {"chatt", "say", "edge", "cosyvoice", "fish"}


def _resolve_backend(settings: Settings) -> str:
    backend = (settings.tts_backend or "chatt").strip().lower()
    if backend == "chatt":
        try:
            import ChatTTS  # noqa: F401
        except ImportError:
            logger.warning("ChatTTS not installed, falling back to macOS say")
            return "say"
        if settings.tts_preload:
            from callio.voice.tts_loader import get_preload_error, is_chatt_ready

            if not is_chatt_ready() and get_preload_error():
                logger.warning("ChatTTS preload failed, falling back to macOS say")
                return "say"
    elif backend not in _KNOWN_BACKENDS:
        logger.warning("Unknown TTS backend %r, falling back to macOS say", backend)
        return "say"
    return backend


def create_tts(settings: Settings | None = None) -> TTSService:
    settings = settings or get_settings()
    backend = _resolve_backend(settings)
    sample_rate = settings.audio_out_sample_rate

    if backend == "chatt":
        return _create_chatt_tts(settings, sample_rate=sample_rate)
    if backend == "edge":
        from callio.voice.edge_tts_backend import create_edge_tts
        return create_edge_tts(settings, sample_rate=sample_rate)
    if backend == "cosyvoice":
        from callio.voice.cosyvoice_tts import create_cosyvoice_tts
        return create_cosyvoice_tts(settings, sample_rate=sample_rate)
    if backend == "fish":
        from callio.voice.fish_tts import create_fish_tts
        return create_fish_tts(settings, sample_rate=sample_rate)
    return _create_say_tts(sample_rate=sample_rate)


def _create_say_tts(*, sample_rate: int) -> TTSService:
    voice = _detect_chinese_voice()

    class MacSayTTSService(TTSService):
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
                wav_bytes = await asyncio.to_thread(synthesize_say_wav, text, self._voice)
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
                logger.info("Streamed assistant audio via say (%d bytes PCM)", len(pcm))
            except Exception as exc:
                logger.warning("macOS say TTS failed: %s", exc)
            yield None

    return MacSayTTSService()


def _create_chatt_tts(settings: Settings, *, sample_rate: int) -> TTSService:
    from callio.voice.tts_loader import synthesize_chatt

    class ChatTTSService(TTSService):
        def __init__(self) -> None:
            super().__init__(
                push_stop_frames=True,
                sample_rate=sample_rate,
                settings=TTSSettings(model="ChatTTS", voice=None, language=Language.ZH),
            )
            self._runtime_settings = settings

        async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
            if not text.strip():
                yield None
                return

            try:
                pcm = await asyncio.to_thread(synthesize_chatt, text, self._runtime_settings)
                if not pcm:
                    yield None
                    return
                for chunk in iter_pcm_chunks(pcm, sample_rate):
                    yield OutputAudioRawFrame(
                        audio=chunk,
                        sample_rate=sample_rate,
                        num_channels=1,
                    )
                logger.info("Streamed assistant audio via ChatTTS (%d bytes PCM)", len(pcm))
            except Exception as exc:
                logger.warning("ChatTTS failed: %s", exc)
            yield None

    return ChatTTSService()


def create_web_audio_tts(*, sample_rate: int = 16000) -> TTSService:
    """Backward-compatible alias."""
    settings = get_settings()
    if settings.audio_out_sample_rate != sample_rate:
        from dataclasses import replace

        settings = replace(settings, audio_out_sample_rate=sample_rate)
    return create_tts(settings)
