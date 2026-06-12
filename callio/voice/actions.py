from __future__ import annotations

from typing import Any


def hermes_tool_definition() -> dict[str, Any]:
    return {
        "name": "execute_hermes_coding",
        "description": "当用户说‘开始落实’时触发，调用后台执行具体代码重构。",
        "properties": {
            "summary": {"type": "string", "description": "头脑风暴得出的功能和架构结论"},
            "actions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "需要修改的文件或动作清单",
            },
        },
        "required": ["summary", "actions"],
    }
