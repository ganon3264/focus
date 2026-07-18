from __future__ import annotations

import json as _json
from typing import Any

from focus.tools import ToolCall, ToolResult, ToolSpec


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


def from_provider_response(choice: Any) -> tuple[str | None, list[ToolCall]]:
    """Extract final text and tool calls from a provider stream choice delta.

    Returns (text_or_None, tool_calls_list). For non-streaming responses,
    inspect choice.message.tool_calls; for streaming, the caller accumulates
    delta.tool_calls and passes the final state here.
    """
    calls: list[ToolCall] = []

    # Non-streaming path (choice.message)
    msg = getattr(choice, "message", None)
    if msg is not None:
        raw_calls = getattr(msg, "tool_calls", None)
        if raw_calls:
            for tc in raw_calls:
                calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=_json.loads(tc.function.arguments) if tc.function.arguments else {},
                    )
                )
        return (msg.content, calls)

    return (None, [])


def to_provider_tool_results(results: list[ToolResult]) -> list[dict]:
    """Convert ToolResult list → tool result messages."""
    return [
        {"role": "tool", "tool_call_id": r.call_id, "content": r.content}
        for r in results
    ]
