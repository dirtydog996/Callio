from __future__ import annotations

import uuid
from typing import Any

from callio.core.database import Database

STDOUT_TAIL_LIMIT = 8000


class TaskLog:
    def __init__(self, database: Database) -> None:
        self.database = database

    def start_run(self, node_id: str, session_id: str, kind: str) -> str:
        run_id = str(uuid.uuid4())
        self.database.insert_task_run(run_id, node_id, session_id, kind, status="RUNNING")
        return run_id

    def append_stdout(self, run_id: str, line: str, *, progress_pct: int | None = None) -> None:
        self.database.append_task_run_stdout(run_id, line, progress_pct=progress_pct, tail_limit=STDOUT_TAIL_LIMIT)

    def finish_run(self, run_id: str, status: str) -> None:
        self.database.finish_task_run(run_id, status)

    def latest_for_session(self, session_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return self.database.list_task_runs(session_id=session_id, limit=limit)
