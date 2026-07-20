from __future__ import annotations

from typing import Any


TOOL_OUTPUT_TRUNCATE_CHARS = 32000
MAX_TOOL_ITERATIONS = 10


def truncate(text: str, max_chars: int = TOOL_OUTPUT_TRUNCATE_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n... [truncated at {max_chars} chars]"


def active_tools(all_tools: list, read_only: bool) -> list:
    if read_only:
        return [t for t in all_tools if not t.writes]
    return all_tools


def build_tool_result(call_id: str, tool_name: str, output: Any) -> Any:
    from focus.tools import ToolResult  # lazy to avoid circular import

    if tool_name == "read_image":
        path, b64_data, mime = output
        return ToolResult(
            call_id=call_id,
            content=f"image read: {path} (attached in next message)",
            extra_message={
                "role": "user",
                "content": [
                    {"type": "text", "text": f"[contents of {path}]"},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64_data}"}},
                ],
                "internal": True,
            },
        )
    return ToolResult(call_id=call_id, content=truncate(str(output)))
