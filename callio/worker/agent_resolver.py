from __future__ import annotations

import shlex
import shutil
from dataclasses import dataclass

from callio.config.settings import Settings, get_settings

# CLI command templates per backend.
# {task} is replaced with the task description.
# Code-oriented backends use a "code" template; daily-task backends may differ.
_TEMPLATES: dict[str, list[str]] = {
    "hermes": ["hermes", "run", "--task", "{task}"],
    "openclaw": ["openclaw", "agent", "--local", "-m", "{task}"],
    "claude": ["claude", "code", "{task}"],
    "aider": ["aider", "--yes-always", "--message", "{task}"],
    "goose": ["goose", "run", "--task", "{task}"],
}

# For daily (non-code) tasks some tools expose a different sub-command.
_DAILY_TEMPLATES: dict[str, list[str]] = {
    "hermes": ["hermes", "run", "--task", "{task}"],
    "openclaw": ["openclaw", "agent", "--local", "-m", "{task}"],
    "claude": ["claude", "{task}"],
    "aider": ["aider", "--yes-always", "--message", "{task}"],
    "goose": ["goose", "run", "--task", "{task}"],
}

# Auto-detect order: prefer lightweight daily-task agents first when no backend is forced.
_DETECT_ORDER = ("hermes", "openclaw", "goose", "aider", "claude")


@dataclass(frozen=True, slots=True)
class ResolvedAgent:
    argv: list[str]
    backend: str


class AgentResolver:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def resolve(self, task: str, *, daily: bool = False) -> ResolvedAgent | None:
        """Resolve the agent command for *task*.

        Args:
            task:  The task description to execute.
            daily: When *True*, use daily-task templates (non-code work such as
                   opening applications, browsing, system operations, etc.).
                   Defaults to *False* (code / engineering tasks).
        """
        custom = (self.settings.agent_command or "").strip()
        if custom:
            return self._from_custom(custom, task)

        backend = (self.settings.agent_backend or "").strip().lower() or self._autodetect()
        if not backend:
            return None
        return self._from_template(backend, task, daily=daily)

    def missing_message(self) -> str:
        names = "/".join(_DETECT_ORDER)
        return (
            f"No coding agent found. Please install one of: {names}, "
            "or set CALLIO_AGENT_BACKEND / CALLIO_AGENT_COMMAND (supports {task})."
        )

    def _from_custom(self, command: str, task: str) -> ResolvedAgent | None:
        if "{task}" in command:
            head, _, tail = command.partition("{task}")
            argv: list[str] = []
            if head.strip():
                argv.extend(shlex.split(head.strip()))
            argv.append(task)
            if tail.strip():
                argv.extend(shlex.split(tail.strip()))
        else:
            argv = shlex.split(command) + [task]
        if not argv or not shutil.which(argv[0]):
            return None
        return ResolvedAgent(argv=argv, backend="custom")

    def _from_template(self, backend: str, task: str, *, daily: bool = False) -> ResolvedAgent | None:
        templates = _DAILY_TEMPLATES if daily else _TEMPLATES
        template = templates.get(backend) or _TEMPLATES.get(backend)
        if not template:
            return None
        argv = [part.format(task=task) for part in template]
        if not shutil.which(argv[0]):
            return None
        return ResolvedAgent(argv=argv, backend=backend)

    @staticmethod
    def _autodetect() -> str:
        for name in _DETECT_ORDER:
            if shutil.which(name):
                return name
        return ""
