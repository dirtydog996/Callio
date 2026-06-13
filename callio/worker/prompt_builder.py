from __future__ import annotations

import json
from typing import Any

from callio.core.database import Database


def build_execute_prompt(database: Database, node_id: str, session_id: str) -> str:
    node = database.get_spec_node(node_id) or {}
    session = database.get_session(session_id) or {}
    actions = _actions_for_node(database, session_id, node_id)

    lines = [
        f"【任务】{node.get('feature_name', '')}",
        f"【说明】{node.get('description', '')}",
    ]
    summary = session.get("summary")
    if summary:
        lines.append(f"【会话摘要】{summary}")
    if actions:
        lines.append("【行动清单】")
        lines.extend(f"- {item}" for item in actions)
    lines.append("请自主修改本地文件并运行测试验证。")
    return "\n".join(lines)


def _actions_for_node(database: Database, session_id: str, node_id: str) -> list[str]:
    for event in database.list_session_events(session_id, limit=80):
        if event.get("kind") != "TASK_PROPOSED":
            continue
        payload = _parse_payload(event.get("payload"))
        if payload.get("node_id") == node_id:
            raw = payload.get("actions") or []
            return [str(item) for item in raw if str(item).strip()]
    return []


def _parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}
