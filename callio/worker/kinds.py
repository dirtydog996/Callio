from __future__ import annotations

from enum import Enum


class TaskKind(str, Enum):
    SUMMARIZE = "SUMMARIZE"
    ANALYZE = "ANALYZE"
    EXECUTE = "EXECUTE"
