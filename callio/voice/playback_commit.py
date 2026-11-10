from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PlaybackCommitTracker:
    """Tracks assistant content that was actually sent to the client for playback."""

    _pending_assistant_text: list[str] = field(default_factory=list)
    _committed_assistant_text: list[str] = field(default_factory=list)
    _audio_chunks_sent: int = 0

    def queue_assistant_text(self, text: str) -> None:
        line = text.strip()
        if line:
            self._pending_assistant_text.append(line)

    def on_audio_chunk_sent(self) -> None:
        self._audio_chunks_sent += 1

    def commit_next_pending(self) -> str | None:
        if not self._pending_assistant_text:
            return None
        line = self._pending_assistant_text.pop(0)
        self._committed_assistant_text.append(line)
        return line

    def on_tts_stopped(self) -> None:
        self._flush_pending()

    def drain_pending_for_commit(self) -> list[str]:
        lines = list(self._pending_assistant_text)
        self._pending_assistant_text.clear()
        return lines

    def _flush_pending(self) -> None:
        while self._pending_assistant_text:
            self._committed_assistant_text.append(self._pending_assistant_text.pop(0))

    def cancel_uncommitted(self) -> list[str]:
        canceled = list(self._pending_assistant_text)
        self._pending_assistant_text.clear()
        self._audio_chunks_sent = 0
        return canceled

    def pop_last_committed_if_needed(self) -> str | None:
        if self._committed_assistant_text:
            return self._committed_assistant_text.pop()
        return None

    @property
    def has_pending(self) -> bool:
        return bool(self._pending_assistant_text)
