from __future__ import annotations

from pipecat.frames.frames import Frame, OutputAudioRawFrame, TTSStoppedFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from callio.config.settings import Settings
from callio.voice.audio_utils import iter_pcm_chunks


class AdaptiveOutputChunker(FrameProcessor):
    """Splits outbound PCM into smaller first chunks to reduce time-to-first-audio."""

    def __init__(
        self,
        settings: Settings,
        *,
        interrupt_controller=None,
        on_audio_sent=None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._first_chunk_ms = settings.latency_first_chunk_ms
        self._next_chunk_ms = settings.latency_subsequent_chunk_ms
        self._awaiting_first_audio = True
        self._interrupt_controller = interrupt_controller
        self._on_audio_sent = on_audio_sent

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TTSStoppedFrame):
            self._awaiting_first_audio = True

        if (
            isinstance(frame, OutputAudioRawFrame)
            and frame.audio
            and direction == FrameDirection.DOWNSTREAM
        ):
            if self._interrupt_controller and getattr(self._interrupt_controller, "hold_tts", False):
                return

            chunk_ms = self._first_chunk_ms if self._awaiting_first_audio else self._next_chunk_ms
            chunks = iter_pcm_chunks(frame.audio, frame.sample_rate, chunk_ms=chunk_ms)
            self._awaiting_first_audio = False
            for chunk in chunks:
                if self._interrupt_controller and getattr(self._interrupt_controller, "hold_tts", False):
                    return
                out = OutputAudioRawFrame(
                    audio=chunk,
                    sample_rate=frame.sample_rate,
                    num_channels=frame.num_channels,
                )
                if self._on_audio_sent:
                    self._on_audio_sent()
                await self.push_frame(out, direction)
            return

        await self.push_frame(frame, direction)
