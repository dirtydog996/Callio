from __future__ import annotations

import shlex
import shutil
from dataclasses import dataclass

from callio.config.settings import Settings, get_settings

_TEMPLATES: dict[str, list[str]] = {
    "hermes": ["hermes", "run", "--task", "{task}"],
    "openclaw": ["openclaw", "agent", "--local", "-m", "{task}"],
    "claude": ["claude", "code", "{task}"],
}
_DETECT_ORDER = ("hermes", "openclaw", "claude")


@dataclass(frozen=True, slots=True)
class ResolvedAgent:
    argv: list[str]
    backend: str


class AgentResolver:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def resolve(self, task: str) -> ResolvedAgent | None:
        custom = (self.settings.agent_command or "").strip()
        if custom:
            return self._from_custom(custom, task)

        backend = (self.settings.agent_backend or "").strip().lower() or self._autodetect()
        if not backend:
            return None
        return self._from_template(backend, task)

    def missing_message(self) -> str:
        return (
            "未找到可用的编码 Agent。请安装 hermes/openclaw/claude，"
            "或设置 CALLIO_AGENT_BACKEND / CALLIO_AGENT_COMMAND（支持 {task}）。"
        )

    def _from_custom(self, command: str, task: str) -> ResolvedAgent | None:
        if "{task}" in command:
            head, _, tail = command.partition("{task}")
            argv = []
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

    def _from_template(self, backend: str, task: str) -> ResolvedAgent | None:
        template = _TEMPLATES.get(backend)
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
