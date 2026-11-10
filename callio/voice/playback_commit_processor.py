from __future__ import annotations

from collections.abc import Callable

from pipecat.frames.frames import Frame, OutputAudioRawFrame, TTSStoppedFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from callio.voice.playback_commit import PlaybackCommitTracker


class PlaybackCommitProcessor(FrameProcessor):
    """Commits assistant transcript lines once audio has reached the outbound path."""

    def __init__(
        self,
        tracker: PlaybackCommitTracker,
        *,
        on_commit: Callable[[str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._tracker = tracker
        self._on_commit = on_commit
        self._committed_audio_for_turn = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TTSStoppedFrame):
            self._committed_audio_for_turn = False

        if isinstance(frame, OutputAudioRawFrame) and frame.audio and direction == FrameDirection.DOWNSTREAM:
            self._tracker.on_audio_chunk_sent()
            if not self._committed_audio_for_turn:
                line = self._tracker.commit_next_pending()
                if line and self._on_commit:
                    self._on_commit(line)
                self._committed_audio_for_turn = True

        await self.push_frame(frame, direction)
