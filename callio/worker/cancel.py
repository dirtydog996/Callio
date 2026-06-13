"""Cancel queued or running worker tasks."""

from __future__ import annotations

from callio.core.database import Database
from callio.worker.task_registry import registry


class TaskCancelService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def cancel_running(self, node_id: str) -> dict[str, object]:
        node = self.database.get_spec_node(node_id)
        if not node:
            return {"cancelled": False, "node_id": node_id, "reason": "not_found"}

        status = str(node.get("status", ""))
        if status in {"SUCCESS", "FAILED", "CANCELLED"}:
            return {"cancelled": False, "node_id": node_id, "status": status, "reason": "terminal"}

        if status in {"PENDING", "QUEUED", "PROPOSED"}:
            self.database.cancel_queued_for_node(node_id)
            self.database.update_spec_status(node_id, "CANCELLED", phase="CANCELLED")
            return {"cancelled": True, "node_id": node_id, "status": "CANCELLED", "mode": "queued"}

        if status == "RUNNING":
            await registry.cancel(node_id)
            self.database.update_spec_status(node_id, "CANCELLED", phase="CANCELLED")
            return {"cancelled": True, "node_id": node_id, "status": "CANCELLED", "mode": "running"}

        self.database.cancel_queued_for_node(node_id)
        self.database.update_spec_status(node_id, "CANCELLED", phase="CANCELLED")
        return {"cancelled": True, "node_id": node_id, "status": "CANCELLED", "mode": "unknown"}
