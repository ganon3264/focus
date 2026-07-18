from __future__ import annotations

from typing import Any

from focus.tools import ToolResult, ToolSpec


def to_provider_tools(tools: list[ToolSpec]) -> list[dict]:
    """Convert internal ToolSpec list → OpenAI-compatible tools= payload."""
    result = []
    for t in tools:
        properties = {}
        for p in t.params:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
        fn = {
            "name": t.name,
            "description": t.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": [p.name for p in t.params if p.required],
            },
        }
        result.append({"type": "function", "function": fn})
    return result



def to_provider_tool_results(results: list[ToolResult]) -> list[dict]:
    """Convert ToolResult list → tool result messages."""
    return [
        {"role": "tool", "tool_call_id": r.call_id, "content": r.content}
        for r in results
    ]
