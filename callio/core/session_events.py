from __future__ import annotations

import json
import uuid
from typing import Any

from callio.core.database import Database


class SessionEventStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def append(self, session_id: str, kind: str, payload: dict[str, Any]) -> str:
        event_id = str(uuid.uuid4())
        self.database.insert_session_event(event_id, session_id, kind, json.dumps(payload, ensure_ascii=False))
        return event_id

    def list_for_session(self, session_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.database.list_session_events(session_id, limit=limit)
        for row in rows:
            if isinstance(row.get("payload"), str):
                try:
                    row["payload"] = json.loads(row["payload"])
                except json.JSONDecodeError:
                    pass
        return rows
