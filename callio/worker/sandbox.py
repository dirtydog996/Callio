from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from callio.config.settings import Settings, get_settings


@dataclass(slots=True)
class SandboxSession:
    workspace: Path
    using_docker: bool
    image: str | None = None


class SandboxManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def prepare_workspace(self, task_id: str) -> SandboxSession:
        workspace = Path(self.settings.sandbox_root).resolve()
        use_docker = self.settings.sandbox_use_docker and shutil.which("docker") is not None
        return SandboxSession(workspace=workspace, using_docker=use_docker, image="callio-worker:latest" if use_docker else None)
