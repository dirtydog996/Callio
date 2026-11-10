from __future__ import annotations

import time

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from callio.config.settings import Settings
from callio.voice.aec import EchoCanceller


class AECConvergenceGuard:
    def __init__(self, settings: Settings, aec: EchoCanceller) -> None:
        self._aec = aec
        self._tts_started_at: float | None = None
        self._convergence_guard_sec = 1.5 if settings.aec_convergence_guard else 0.0

    def on_tts_started(self) -> None:
        self._tts_started_at = time.monotonic()
        self._aec.mark_tts_started()

    def on_tts_stopped(self) -> None:
        self._tts_started_at = None
        self._aec.notify_converged()

    def tick_after_mic(self) -> None:
        if (
            self._aec.enabled
            and self._tts_started_at is not None
            and (time.monotonic() - self._tts_started_at) >= self._convergence_guard_sec
        ):
            self._aec.notify_converged()

    @property
    def barge_in_dampened(self) -> bool:
        if not self._aec.enabled or self._convergence_guard_sec <= 0:
            return False
        if self._tts_started_at is None:
            return False
        if self._aec.converged:
            return False
        return (time.monotonic() - self._tts_started_at) < self._convergence_guard_sec


class AECInputProcessor(FrameProcessor):
    """Cleans inbound microphone audio using a shared echo canceller."""

    def __init__(self, aec: EchoCanceller, guard: AECConvergenceGuard, **kwargs) -> None:
        super().__init__(**kwargs)
        self._aec = aec
        self._guard = guard

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.UPSTREAM and isinstance(frame, InputAudioRawFrame) and frame.audio:
            if self._aec.enabled:
                frame.audio = self._aec.process_mic_pcm(frame.audio)
            self._guard.tick_after_mic()
        await self.push_frame(frame, direction)


class AECReferenceProcessor(FrameProcessor):
    """Feeds outbound TTS audio into the echo canceller reference buffer."""

    def __init__(self, aec: EchoCanceller, guard: AECConvergenceGuard, **kwargs) -> None:
        super().__init__(**kwargs)
        self._aec = aec
        self._guard = guard

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSStartedFrame):
            self._guard.on_tts_started()
        elif isinstance(frame, TTSStoppedFrame):
            self._guard.on_tts_stopped()
        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, OutputAudioRawFrame) and frame.audio:
            self._aec.push_reference_pcm(frame.audio)
        await self.push_frame(frame, direction)
