from __future__ import annotations

import logging

from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.aggregators.llm_response_universal import LLMUserAggregatorParams
from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies, default_user_turn_start_strategies

from callio.config.settings import Settings

logger = logging.getLogger(__name__)

# Pipecat empty-turn recovery injects role=developer; many OpenAI-compatible APIs reject it.
_LLM_DEVELOPER_ROLE_PROVIDERS = frozenset({"openai", "anthropic", "gemini"})


def build_vad_analyzer(settings: Settings) -> SileroVADAnalyzer:
    return SileroVADAnalyzer(
        params=VADParams(
            start_secs=0.18,
            stop_secs=settings.vad_stop_secs,
            min_volume=0.25,
        )
    )


def estimate_stt_ttfs_p99(settings: Settings) -> float:
    """Rough TTFS P99 for pipecat turn timing (aligns with VAD + local STT)."""
    backend = (settings.stt_backend or "whisper").strip().lower()
    base = max(0.2, settings.vad_stop_secs) + 0.8
    if backend == "sensevoice":
        return base + 1.2 if settings.funasr_streaming else base + 2.0
    model = (settings.whisper_model or "small").lower()
    if model in {"tiny", "base"}:
        return base + 1.0
    return base + 1.6


def build_smart_turn_analyzer(settings: Settings) -> LocalSmartTurnAnalyzerV3 | None:
    if not settings.semantic_eou_enabled:
        return None
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        logger.warning("semantic EOU requested but onnxruntime is not installed; falling back to VAD timeout")
        return None

    path = (settings.smart_turn_model_path or "").strip() or None
    cpu = max(1, settings.smart_turn_cpu_threads)
    return LocalSmartTurnAnalyzerV3(smart_turn_model_path=path, cpu_count=cpu)


def build_user_aggregator_params(settings: Settings) -> LLMUserAggregatorParams:
    vad = build_vad_analyzer(settings)
    turn = build_smart_turn_analyzer(settings)
    if turn is not None:
        stop = [TurnAnalyzerUserTurnStopStrategy(turn_analyzer=turn)]
        logger.info("ONNX Smart Turn v3 EOU enabled")
    else:
        stop = [SpeechTimeoutUserTurnStopStrategy()]
    strategies = UserTurnStrategies(
        start=default_user_turn_start_strategies(),
        stop=stop,
    )
    provider = (settings.llm_provider or "ollama").strip().lower()
    empty_user_turn = None
    if provider in _LLM_DEVELOPER_ROLE_PROVIDERS:
        from pipecat.turns.empty_user_turn import EmptyUserTurnConfig

        empty_user_turn = EmptyUserTurnConfig()

    return LLMUserAggregatorParams(
        vad_analyzer=vad,
        user_turn_strategies=strategies,
        audio_idle_timeout=1.0,
        empty_user_turn=empty_user_turn,
    )
