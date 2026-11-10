from __future__ import annotations

from dataclasses import replace

from callio.config.settings import Settings
from callio.voice.smart_turn_factory import build_user_aggregator_params, build_vad_analyzer


def test_build_vad_analyzer():
    settings = Settings(vad_stop_secs=0.35)
    vad = build_vad_analyzer(settings)
    assert vad.params.stop_secs == 0.35


def test_user_params_without_semantic_eou():
    settings = replace(Settings(), semantic_eou_enabled=False)
    params = build_user_aggregator_params(settings)
    assert params.vad_analyzer is not None
    assert params.user_turn_strategies is not None
    assert len(params.user_turn_strategies.stop or []) == 1
