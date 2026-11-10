from __future__ import annotations

from callio.config.latency_budget import DEFAULT_LATENCY_BUDGET, check_budget, summarize_turn_metrics
from callio.voice.latency import LatencyRecorder, TurnTimestamps
from callio.voice.turn_endpointing import is_backchannel, recommended_endpoint_delay, semantic_eou_probability


def test_turn_derived_metrics():
    turn = TurnTimestamps(
        turn_id=1,
        t_user_speech_end=100.0,
        t_stt_final=320.0,
        t_llm_first_token=500.0,
        t_tts_first_chunk=680.0,
        t_audio_sent=700.0,
    )
    derived = turn.derived()
    assert derived["first_response_ms"] == 600.0
    assert derived["stt_after_speech_end_ms"] == 220.0
    assert derived["tts_first_chunk_ms"] == 180.0


def test_latency_recorder_finalize():
    recorder = LatencyRecorder()
    recorder.begin_turn()
    recorder.mark("t_user_speech_end")
    recorder.mark("t_stt_final")
    turn = recorder.finalize_turn()
    assert turn is not None
    assert len(recorder.turns) == 1


def test_budget_passes_when_within_limits():
    turns = [
        {
            "derived": {
                "stt_after_speech_end_ms": 200,
                "llm_first_token_ms": 250,
                "tts_first_chunk_ms": 180,
                "first_response_ms": 700,
                "interrupt_response_ms": 150,
            }
        }
        for _ in range(5)
    ]
    summary = summarize_turn_metrics(turns)
    passed, checks = check_budget(summary, DEFAULT_LATENCY_BUDGET)
    assert passed
    assert all(c["pass"] for c in checks)


def test_backchannel_detection():
    assert is_backchannel("嗯")
    assert is_backchannel("好的！")
    assert not is_backchannel("帮我查一下天气")


def test_semantic_eou_adjusts_delay():
    p = semantic_eou_probability(silence_sec=0.5, had_speech_sec=3.0, semantic_eou_enabled=True)
    delay = recommended_endpoint_delay(0.4, eou_probability=p)
    assert 0.25 <= delay <= 1.2
