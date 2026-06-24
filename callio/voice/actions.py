"""Legacy Hermes tool — superseded by voice/tools (propose_tasks + confirm_tasks)."""

from __future__ import annotations

from callio.voice.tools.schemas import all_tool_definitions


def hermes_tool_definition() -> dict:
    """Backward-compatible alias; returns first orchestrator tool shape."""
    tools = all_tool_definitions()
    return tools[0] if tools else {
        "name": "propose_tasks",
        "description": "Propose background tasks",
        "properties": {"tasks": {"type": "array", "items": {"type": "object"}}},
        "required": ["tasks"],
    }
