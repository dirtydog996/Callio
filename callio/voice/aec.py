from __future__ import annotations

import logging
from collections import deque

import numpy as np

from callio.config.settings import Settings

logger = logging.getLogger(__name__)

_REFERENCE_BLOCK_SAMPLES = 160  # 10ms @ 16kHz


class EchoCanceller:
    """Optional WebRTC AEC3 wrapper with reference-ring buffering for TTS playback."""

    def __init__(self, settings: Settings, *, sample_rate: int = 16000) -> None:
        self._sample_rate = sample_rate
        self._enabled = settings.aec_enabled
        self._stream_delay_ms = settings.aec_stream_delay_ms
        self._apm = None
        self._reference: deque[np.ndarray] = deque()
        self._ref_capacity = int(sample_rate * 2)  # ~2s of 10ms blocks
        self._converged = not self._enabled

        if not self._enabled:
            return

        try:
            from webrtc_audio_processing import AudioProcessing, APConfig

            config = APConfig()
            config.echo_canceller_enabled = True
            config.noise_suppression_enabled = True
            config.high_pass_filter_enabled = True
            config.gain_controller_enabled = True
            self._apm = AudioProcessing(config)
            logger.info(
                "AEC enabled (stream_delay_ms=%d)",
                self._stream_delay_ms,
            )
        except Exception as exc:
            try:
                import pywebrtc_audio as pwa

                self._apm = pwa.AudioProcessingModule(
                    enable_aec=True,
                    enable_ns=True,
                    enable_agc=True,
                    enable_hpf=True,
                )
                logger.info("AEC enabled via pywebrtc-audio")
            except Exception:
                logger.warning("AEC requested but no backend available: %s", exc)
                self._enabled = False
                self._converged = True

    @property
    def enabled(self) -> bool:
        return self._enabled and self._apm is not None

    @property
    def converged(self) -> bool:
        return self._converged

    def mark_tts_started(self) -> None:
        if self.enabled:
            self._converged = False

    def notify_converged(self) -> None:
        self._converged = True

    def push_reference_pcm(self, pcm: bytes) -> None:
        if not self.enabled or not pcm:
            return
        samples = np.frombuffer(pcm, dtype=np.int16)
        step = _REFERENCE_BLOCK_SAMPLES
        for i in range(0, len(samples), step):
            block = samples[i : i + step]
            if len(block) < step:
                block = np.pad(block, (0, step - len(block)))
            self._reference.append(block.astype(np.int16))
            while len(self._reference) > self._ref_capacity // step:
                self._reference.popleft()

    def process_mic_pcm(self, pcm: bytes) -> bytes:
        if not self.enabled or not pcm:
            return pcm

        mic = np.frombuffer(pcm, dtype=np.int16).copy()
        step = _REFERENCE_BLOCK_SAMPLES
        out = np.empty_like(mic)

        for offset in range(0, len(mic), step):
            block = mic[offset : offset + step]
            if len(block) < step:
                block = np.pad(block, (0, step - len(block)))

            ref = self._reference.popleft() if self._reference else np.zeros(step, dtype=np.int16)
            cleaned = self._process_block(block, ref)
            end = min(offset + step, len(out))
            out[offset:end] = cleaned[: end - offset]

        return out.astype(np.int16).tobytes()

    def _process_block(self, mic: np.ndarray, ref: np.ndarray) -> np.ndarray:
        try:
            if hasattr(self._apm, "process_reverse_stream"):
                self._apm.process_reverse_stream(ref.tobytes(), self._sample_rate, 1)
                return np.frombuffer(
                    self._apm.process_stream(mic.tobytes(), self._sample_rate, 1),
                    dtype=np.int16,
                )
            if hasattr(self._apm, "process_stream"):
                self._apm.process_reverse(ref.tobytes(), self._sample_rate)
                return np.frombuffer(
                    self._apm.process(mic.tobytes(), self._sample_rate),
                    dtype=np.int16,
                )
        except Exception as exc:
            logger.debug("AEC frame failed: %s", exc)
        return mic
