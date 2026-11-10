"""Pipecat segmented STT helpers without importing pipecat.services.whisper.stt.

Pipecat 1.15 imports mlx_whisper at module load time on Darwin arm64, which breaks
Callio deployments that use faster-whisper / FunASR only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipecat.services.settings import STTSettings
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.transcriptions.language import Language, resolve_language
from pipecat.utils.types import NOT_GIVEN, NotGiven


def language_to_whisper_language(language: Language) -> str:
    """Map pipecat Language to Whisper language codes (subset pipecat uses)."""
    language_map = {
        Language.AR: "ar",
        Language.BN: "bn",
        Language.CS: "cs",
        Language.DA: "da",
        Language.DE: "de",
        Language.EL: "el",
        Language.EN: "en",
        Language.ES: "es",
        Language.FA: "fa",
        Language.FI: "fi",
        Language.FR: "fr",
        Language.HI: "hi",
        Language.HU: "hu",
        Language.ID: "id",
        Language.IT: "it",
        Language.JA: "ja",
        Language.KO: "ko",
        Language.NL: "nl",
        Language.PL: "pl",
        Language.PT: "pt",
        Language.RO: "ro",
        Language.RU: "ru",
        Language.SK: "sk",
        Language.SV: "sv",
        Language.TH: "th",
        Language.TR: "tr",
        Language.UK: "uk",
        Language.UR: "ur",
        Language.VI: "vi",
        Language.ZH: "zh",
    }
    return resolve_language(language, language_map, use_base_code=True)


@dataclass
class CallioWhisperSTTSettings(STTSettings):
    """Whisper-style STT settings used by Callio local backends."""

    no_speech_prob: float | NotGiven = field(default_factory=lambda: NOT_GIVEN)
    hotwords: str | None | NotGiven = field(default_factory=lambda: NOT_GIVEN)
    initial_prompt: str | None | NotGiven = field(default_factory=lambda: NOT_GIVEN)


class CallioSegmentedSTTService(SegmentedSTTService):
    """Segmented local STT base: raw PCM segments, no mlx_whisper import."""

    Settings = CallioWhisperSTTSettings

    @property
    def wants_wav_segments(self) -> bool:
        return False

    def __init__(
        self,
        *,
        settings: CallioWhisperSTTSettings | None = None,
        ttfs_p99_latency: float = 2.0,
        **kwargs,
    ) -> None:
        default_settings = CallioWhisperSTTSettings(
            model="base",
            language=Language.ZH,
            no_speech_prob=0.6,
        )
        if settings is not None:
            default_settings.apply_update(settings)
        super().__init__(settings=default_settings, ttfs_p99_latency=ttfs_p99_latency, **kwargs)
        self._model = None
