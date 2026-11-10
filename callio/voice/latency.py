from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


def _mono_ms(origin: float) -> float:
    return (time.monotonic() - origin) * 1000.0


@dataclass(slots=True)
class TurnTimestamps:
    turn_id: int = 0
    t_user_speech_end: float | None = None
    t_stt_final: float | None = None
    t_llm_first_token: float | None = None
    t_tts_first_chunk: float | None = None
    t_audio_sent: float | None = None
    t_interrupt_detected: float | None = None
    t_audio_stop: float | None = None

    def derived(self) -> dict[str, float | None]:
        def delta(a: float | None, b: float | None) -> float | None:
            if a is None or b is None:
                return None
            return a - b

        return {
            "first_response_ms": delta(self.t_audio_sent, self.t_user_speech_end),
            "stt_after_speech_end_ms": delta(self.t_stt_final, self.t_user_speech_end),
            "llm_first_token_ms": delta(self.t_llm_first_token, self.t_stt_final),
            "tts_first_chunk_ms": delta(self.t_tts_first_chunk, self.t_llm_first_token),
            "stt_to_first_audio_ms": delta(self.t_audio_sent, self.t_stt_final),
            "interrupt_response_ms": delta(self.t_audio_stop, self.t_interrupt_detected),
        }


@dataclass
class LatencyRecorder:
    """Per-connection latency timestamps using a monotonic clock origin."""

    _origin: float = field(default_factory=time.monotonic)
    _turn_id: int = 0
    _current: TurnTimestamps = field(default_factory=TurnTimestamps)
    turns: list[TurnTimestamps] = field(default_factory=list)

    def now_ms(self) -> float:
        return _mono_ms(self._origin)

    def begin_turn(self) -> None:
        self._turn_id += 1
        self._current = TurnTimestamps(turn_id=self._turn_id)

    def mark(self, field_name: str) -> float:
        ts = self.now_ms()
        if not hasattr(self._current, field_name):
            raise ValueError(f"unknown latency field: {field_name}")
        current = getattr(self._current, field_name)
        if current is None:
            setattr(self._current, field_name, ts)
        return ts

    def is_unset(self, field_name: str) -> bool:
        return getattr(self._current, field_name, None) is None

    def on_user_speech_end(self) -> None:
        if self._current.t_user_speech_end is None:
            self.begin_turn()
        self.mark("t_user_speech_end")

    def finalize_turn(self) -> TurnTimestamps | None:
        if self._current.t_user_speech_end is None:
            return None
        snapshot = self._current
        self.turns.append(snapshot)
        self._current = TurnTimestamps(turn_id=self._turn_id)
        return snapshot

    def export_turn(self, turn: TurnTimestamps) -> dict[str, Any]:
        payload = asdict(turn)
        payload["derived"] = turn.derived()
        return payload

    def export_baseline(self) -> dict[str, Any]:
        return {
            "captured_at_unix": time.time(),
            "turns": [self.export_turn(t) for t in self.turns],
        }
