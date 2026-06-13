from __future__ import annotations

from typing import Any

from callio.config.settings import Settings
from callio.core.database import Database


class ProgressSnapshot:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    def snapshot(self, session_id: str) -> dict[str, Any]:
        nodes = self.database.list_spec_nodes(session_id=session_id)
        runs = self.database.list_task_runs(session_id=session_id, limit=5)
        session = self.database.get_session(session_id)

        by_status: dict[str, int] = {}
        proposed: list[dict[str, str]] = []
        active: list[dict[str, str]] = []
        done: list[dict[str, str]] = []

        for node in nodes:
            status = str(node.get("status") or "")
            phase = str(node.get("phase") or "")
            by_status[status] = by_status.get(status, 0) + 1
            item = {
                "node_id": str(node.get("node_id")),
                "title": str(node.get("feature_name")),
                "kind": str(node.get("kind")),
                "status": status,
                "phase": phase,
            }
            if phase == "PROPOSED":
                proposed.append(item)
            elif status == "RUNNING":
                active.append(item)
            elif status in {"SUCCESS", "FAILED", "CANCELLED"}:
                done.append(item)

        last_log = ""
        if runs:
            last_log = str(runs[0].get("stdout_tail") or "")[-300:]

        return {
            "session_id": session_id,
            "summary": (session or {}).get("summary"),
            "action_plan": (session or {}).get("action_plan"),
            "proposed": proposed,
            "active": active,
            "done": done[:5],
            "counts": by_status,
            "last_log": last_log,
        }

    def build_context_block(self, session_id: str) -> str:
        if not self.settings.progress_inject:
            return ""
        snap = self.snapshot(session_id)
        parts: list[str] = []
        if snap.get("summary"):
            parts.append(f"摘要: {snap['summary']}")
        if snap.get("action_plan"):
            parts.append(f"计划: {snap['action_plan']}")
        if snap.get("proposed"):
            titles = ", ".join(f"{t['title']}(待确认)" for t in snap["proposed"][:3])
            parts.append(f"待确认: {titles}")
        if snap.get("active"):
            titles = ", ".join(f"{t['title']}({t['status']})" for t in snap["active"][:3])
            parts.append(f"进行中: {titles}")
        if snap.get("done"):
            titles = ", ".join(f"{t['title']}({t['status']})" for t in snap["done"][:3])
            parts.append(f"已完成: {titles}")
        if snap.get("last_log"):
            parts.append(f"最近日志: {snap['last_log'][:120]}")
        if not parts:
            return ""
        return "【后台任务状态】" + " | ".join(parts)
