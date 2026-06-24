from __future__ import annotations

from typing import Any


def all_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "propose_tasks",
            "description": "Propose one or more background tasks (analysis/coding, etc.). After calling, you MUST read the task list aloud to the user and wait for confirmation. Do NOT execute directly.",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Task title"},
                            "description": {"type": "string", "description": "Detailed task description"},
                            "kind": {
                                "type": "string",
                                "enum": ["EXECUTE", "ANALYZE"],
                                "description": "EXECUTE=coding implementation, ANALYZE=read-only analysis",
                            },
                            "actions": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Specific action items for EXECUTE tasks",
                            },
                        },
                        "required": ["title", "description"],
                    },
                    "description": "List of tasks to propose",
                }
            },
            "required": ["tasks"],
        },
        {
            "name": "confirm_tasks",
            "description": "Confirm and dispatch proposed tasks in parallel once the user explicitly agrees (e.g. 'yes', 'start', 'confirm').",
            "properties": {
                "node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "node_id list returned by propose_tasks; can be omitted when confirm_all=true",
                },
                "confirm_all": {
                    "type": "boolean",
                    "description": "Confirm all pending proposed tasks for this session",
                },
            },
            "required": [],
        },
        {
            "name": "cancel_proposal",
            "description": "Cancel unconfirmed proposed tasks.",
            "properties": {
                "node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "node_id list to cancel",
                }
            },
            "required": ["node_ids"],
        },
        {
            "name": "get_session_progress",
            "description": "Query progress, summary, and recent logs of all background tasks in the current session to report to the user.",
            "properties": {},
            "required": [],
        },
        {
            "name": "propose_summary",
            "description": "Generate a summary and action plan draft from the current conversation (runs in background, non-blocking).",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "Optional focus hint for the summary",
                }
            },
            "required": [],
        },
    ]
