from __future__ import annotations

import os
import shutil
from pathlib import Path

from callio.config.settings import Settings, get_settings
from callio.meta.sanity_checker import SanityChecker, SanityResult


class ShadowManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.source_root = Path(self.settings.sandbox_root).resolve()
        self.shadow_root = Path(self.settings.shadow_root).resolve()
        self.active_link = self.shadow_root.parent / "active"

    def prepare_shadow_copy(self) -> Path:
        if self.shadow_root.exists():
            shutil.rmtree(self.shadow_root)
        shutil.copytree(self.source_root, self.shadow_root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".callio_shadow"))
        return self.shadow_root

    def validate_shadow(self, app: object | None = None) -> SanityResult:
        return SanityChecker(self.settings).run(app)

    def promote_shadow(self) -> None:
        self.active_link.parent.mkdir(parents=True, exist_ok=True)
        if self.active_link.is_symlink() or self.active_link.exists():
            self.active_link.unlink()
        os.symlink(self.shadow_root, self.active_link)
