from __future__ import annotations

from callio.core.database import Database
from callio.core.memory import MemoryHub


def build_memory_block(
    memory_hub: MemoryHub,
    database: Database,
    *,
    query: str = "会话摘要 行动计划 编码任务 决策",
    limit: int = 5,
) -> str:
    lines: list[str] = []
    hits = memory_hub.search_semantic_memory(query, limit=limit)
    if hits:
        lines.append("【历史记忆】")
        for hit in hits:
            content = str(hit.get("content", "")).strip()
            if content:
                lines.append(f"- {content[:240]}")

    for session in database.list_sessions()[:5]:
        plan = str(session.get("action_plan", "")).strip()
        if not plan:
            continue
        title = str(session.get("title", session.get("session_id", "")))
        lines.append(f"【未完成计划 · {title}】\n{plan[:400]}")
        break

    return "\n\n".join(lines)
