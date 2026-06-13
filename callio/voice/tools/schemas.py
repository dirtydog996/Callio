from __future__ import annotations

from typing import Any


def all_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "propose_tasks",
            "description": "向用户提议一项或多项后台任务（分析/编码等）。调用后必须用口语向用户朗读任务清单并等待确认，禁止直接执行。",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "任务标题"},
                            "description": {"type": "string", "description": "任务详细说明"},
                            "kind": {
                                "type": "string",
                                "enum": ["EXECUTE", "ANALYZE"],
                                "description": "EXECUTE=编码实现，ANALYZE=只读分析",
                            },
                            "actions": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "EXECUTE 时的具体行动清单",
                            },
                        },
                        "required": ["title", "description"],
                    },
                    "description": "待提议任务列表",
                }
            },
            "required": ["tasks"],
        },
        {
            "name": "confirm_tasks",
            "description": "用户明确同意（如「可以」「开始」「确认」）后，确认并并行派发已提议的任务。",
            "properties": {
                "node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "propose_tasks 返回的 node_id 列表；confirm_all=true 时可省略",
                },
                "confirm_all": {
                    "type": "boolean",
                    "description": "确认该会话全部待确认任务",
                },
            },
            "required": [],
        },
        {
            "name": "cancel_proposal",
            "description": "取消尚未确认的提议任务。",
            "properties": {
                "node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要取消的 node_id 列表",
                }
            },
            "required": ["node_ids"],
        },
        {
            "name": "get_session_progress",
            "description": "查询当前会话所有后台任务进度、摘要与最近日志，用于向用户汇报进展。",
            "properties": {},
            "required": [],
        },
        {
            "name": "propose_summary",
            "description": "根据当前通话内容生成摘要与行动计划草案（后台执行，不阻塞通话）。",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "可选，摘要侧重点",
                }
            },
            "required": [],
        },
    ]
