from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from callio.config.settings import Settings, get_settings


@dataclass(slots=True)
class SanityResult:
    api_test: float
    vad_init: float
    database_migrate: float

    @property
    def score(self) -> float:
        return round(0.3 * self.api_test + 0.4 * self.vad_init + 0.3 * self.database_migrate, 3)

    @property
    def passed(self) -> bool:
        return self.score == 1.0


class SanityChecker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(self, app: Any | None = None) -> SanityResult:
        api_ok = 1.0 if app is not None and hasattr(app, "routes") else 0.0
        db_ok = 1.0 if Path(self.settings.db_path).exists() else 0.0
        vad_ok = 1.0 if self._vad_importable() else 0.0
        return SanityResult(api_test=api_ok, vad_init=vad_ok, database_migrate=db_ok)

    @staticmethod
    def _vad_importable() -> bool:
        try:
            import pipecat  # noqa: F401
        except Exception:
            return 0.0 == 1.0
        return True
