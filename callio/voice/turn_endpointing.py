from __future__ import annotations

import re

_BACKCHANNEL_RE = re.compile(
    r"^(嗯|嗯嗯|对|对对|好|好的|是的|行|可以|哦|啊|唔|嗯哼|mhmm|uh|um|yeah|yes|ok|okay)[。！？!.?]*$",
    re.IGNORECASE,
)


def is_backchannel(text: str) -> bool:
    return bool(_BACKCHANNEL_RE.match(text.strip()))


def semantic_eou_probability(
    *,
    silence_sec: float,
    had_speech_sec: float,
    semantic_eou_enabled: bool,
) -> float:
    """Lightweight placeholder until an ONNX EOU model is wired in.

    When disabled, mimics pure temporal endpointing (high EOU after vad_stop).
    When enabled, hesitations (short silence, longer prior speech) lower EOU.
    """
    if not semantic_eou_enabled:
        return 1.0 if silence_sec >= 0.35 else 0.2

    if silence_sec < 0.25:
        return 0.1
    if had_speech_sec > 2.5 and silence_sec < 0.6:
        return 0.35
    if silence_sec >= 0.45:
        return 0.92
    return 0.55


def recommended_endpoint_delay(
    base_stop_secs: float,
    *,
    eou_probability: float,
    min_stop_secs: float = 0.25,
    max_stop_secs: float = 1.2,
) -> float:
    if eou_probability >= 0.85:
        return max(min_stop_secs, base_stop_secs * 0.85)
    if eou_probability < 0.4:
        return min(max_stop_secs, base_stop_secs * 1.6)
    return base_stop_secs
