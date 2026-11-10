from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMTextFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from callio.voice.latency import LatencyRecorder

logger = logging.getLogger(__name__)


class LatencyProcessor(FrameProcessor):
    def __init__(
        self,
        recorder: LatencyRecorder,
        *,
        emit_event: Callable[[dict], Awaitable[None]] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._recorder = recorder
        self._emit_event = emit_event
        self._assistant_responding = False

    def mark_interrupt(self) -> None:
        self._recorder.mark("t_interrupt_detected")

    def mark_audio_stopped(self) -> None:
        self._recorder.mark("t_audio_stop")

    async def _finalize_turn(self) -> None:
        turn = self._recorder.finalize_turn()
        if turn is None or self._emit_event is None:
            return
        payload = {
            "type": "latency",
            "turn_id": turn.turn_id,
            "timestamps_ms": {
                k: v
                for k, v in turn.__dict__.items()
                if k != "turn_id" and v is not None
            },
            "derived_ms": turn.derived(),
        }
        try:
            await self._emit_event(payload)
        except Exception as exc:
            logger.debug("latency event emit failed: %s", exc)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            self._recorder.on_user_speech_end()
            self._assistant_responding = False

        elif isinstance(frame, TranscriptionFrame) and frame.text:
            self._recorder.mark("t_stt_final")

        elif isinstance(frame, LLMTextFrame) and frame.text:
            if self._recorder.is_unset("t_llm_first_token"):
                self._recorder.mark("t_llm_first_token")

        elif isinstance(frame, (TTSAudioRawFrame, OutputAudioRawFrame)) and frame.audio:
            if self._recorder.is_unset("t_tts_first_chunk"):
                self._recorder.mark("t_tts_first_chunk")
            if direction == FrameDirection.DOWNSTREAM and self._recorder.is_unset("t_audio_sent"):
                self._recorder.mark("t_audio_sent")

        elif isinstance(frame, InterruptionFrame):
            self.mark_interrupt()

        elif isinstance(frame, TTSStoppedFrame):
            self._assistant_responding = False
            asyncio.create_task(self._finalize_turn())

        await self.push_frame(frame, direction)
