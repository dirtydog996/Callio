from __future__ import annotations

import logging
import time

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    TranscriptionFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from callio.config.settings import Settings
from callio.voice.turn_endpointing import is_backchannel

logger = logging.getLogger(__name__)


class InterruptController(FrameProcessor):
    """Two-stage barge-in: acoustic onset, then semantic/backchannel confirmation."""

    def __init__(
        self,
        settings: Settings,
        *,
        convergence_guard=None,
        on_interrupt_detected=None,
        on_audio_stopped=None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._settings = settings
        self._convergence_guard = convergence_guard
        self._on_interrupt_detected = on_interrupt_detected
        self._on_audio_stopped = on_audio_stopped
        self._assistant_speaking = False
        self._candidate_since: float | None = None
        self._hold_tts = False
        self._onset_ms = settings.barge_in_onset_ms
        self._vad_started_at: float | None = None

    @property
    def hold_tts(self) -> bool:
        return self._hold_tts

    def _aec_dampened(self) -> bool:
        if self._convergence_guard is None:
            return False
        return self._convergence_guard.barge_in_dampened

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TTSStartedFrame):
            self._assistant_speaking = True
        elif isinstance(frame, TTSStoppedFrame):
            self._assistant_speaking = False
            self._clear_candidate()

        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._vad_started_at = time.monotonic()
            if self._assistant_speaking and not self._aec_dampened():
                if self._onset_ms <= 0:
                    await self._confirm_interrupt()
                else:
                    self._candidate_since = time.monotonic()
                    self._hold_tts = True
            elif not self._assistant_speaking:
                await self.broadcast_frame(InterruptionFrame)

        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._vad_started_at = None
            if self._hold_tts and self._candidate_since is not None:
                self._clear_candidate()

        elif isinstance(frame, TranscriptionFrame) and frame.text and self._candidate_since is not None:
            text = frame.text.strip()
            if is_backchannel(text):
                logger.debug("Barge-in candidate dismissed as backchannel: %s", text)
                self._clear_candidate()
            else:
                await self._confirm_interrupt()

        if (
            self._candidate_since is not None
            and self._vad_started_at is not None
            and not self._aec_dampened()
        ):
            elapsed_ms = (time.monotonic() - self._vad_started_at) * 1000.0
            if elapsed_ms >= self._onset_ms:
                await self._confirm_interrupt()

        await self.push_frame(frame, direction)

    def _clear_candidate(self) -> None:
        self._candidate_since = None
        self._hold_tts = False
        self._vad_started_at = None

    async def _confirm_interrupt(self) -> None:
        if not self._assistant_speaking and self._candidate_since is None:
            return
        if self._on_interrupt_detected:
            self._on_interrupt_detected()
        if self._on_audio_stopped:
            self._on_audio_stopped()
        await self.broadcast_frame(InterruptionFrame)
        self._clear_candidate()
