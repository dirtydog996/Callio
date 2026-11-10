from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StageBudget:
    median_ms: float
    p90_ms: float


@dataclass(frozen=True, slots=True)
class LatencyBudget:
    stt_stable_after_speech_end: StageBudget
    llm_first_token: StageBudget
    tts_first_chunk: StageBudget
    end_to_end_first_audio: StageBudget
    interrupt_response: StageBudget


DEFAULT_LATENCY_BUDGET = LatencyBudget(
    stt_stable_after_speech_end=StageBudget(250, 400),
    llm_first_token=StageBudget(300, 600),
    tts_first_chunk=StageBudget(200, 350),
    end_to_end_first_audio=StageBudget(750, 1000),
    interrupt_response=StageBudget(200, 350),
)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def summarize_turn_metrics(turns: list[dict[str, Any]]) -> dict[str, Any]:
    def col(key: str) -> list[float]:
        out: list[float] = []
        for turn in turns:
            val = turn.get("derived", {}).get(key)
            if isinstance(val, (int, float)):
                out.append(float(val))
        return out

    def stage_summary(key: str) -> dict[str, float | None]:
        values = col(key)
        return {
            "median_ms": _percentile(values, 50),
            "p90_ms": _percentile(values, 90),
            "count": len(values),
        }

    return {
        "stt_after_speech_end_ms": stage_summary("stt_after_speech_end_ms"),
        "llm_first_token_ms": stage_summary("llm_first_token_ms"),
        "tts_first_chunk_ms": stage_summary("tts_first_chunk_ms"),
        "first_response_ms": stage_summary("first_response_ms"),
        "interrupt_response_ms": stage_summary("interrupt_response_ms"),
        "turns": len(turns),
    }


def check_budget(
    summary: dict[str, Any],
    budget: LatencyBudget = DEFAULT_LATENCY_BUDGET,
) -> tuple[bool, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []

    def add(name: str, measured: dict[str, Any] | None, stage: StageBudget) -> None:
        median = measured.get("median_ms") if measured else None
        p90 = measured.get("p90_ms") if measured else None
        ok = True
        if median is not None and median > stage.median_ms:
            ok = False
        if p90 is not None and p90 > stage.p90_ms:
            ok = False
        checks.append(
            {
                "stage": name,
                "median_ms": median,
                "median_budget_ms": stage.median_ms,
                "p90_ms": p90,
                "p90_budget_ms": stage.p90_ms,
                "pass": ok and measured is not None and measured.get("count", 0) > 0,
            }
        )

    add(
        "stt_stable_after_speech_end",
        summary.get("stt_after_speech_end_ms"),
        budget.stt_stable_after_speech_end,
    )
    add("llm_first_token", summary.get("llm_first_token_ms"), budget.llm_first_token)
    add("tts_first_chunk", summary.get("tts_first_chunk_ms"), budget.tts_first_chunk)
    add(
        "end_to_end_first_audio",
        summary.get("first_response_ms"),
        budget.end_to_end_first_audio,
    )
    add(
        "interrupt_response",
        summary.get("interrupt_response_ms"),
        budget.interrupt_response,
    )
    passed = all(item["pass"] for item in checks)
    return passed, checks
