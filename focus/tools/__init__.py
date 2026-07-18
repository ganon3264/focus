from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ToolParam:
    name: str
    type: str
    description: str
    required: bool = True
    enum: list[str] | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    params: list[ToolParam]
    writes: bool
    handler: Callable[..., Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False
    extra_message: dict | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

MAX_TOOL_ITERATIONS = 10
TOOL_OUTPUT_TRUNCATE_CHARS = 32000


def active_tools(all_tools: list[ToolSpec], read_only: bool) -> list[ToolSpec]:
    if read_only:
        return [t for t in all_tools if not t.writes]
    return all_tools


def build_tool_result(call_id: str, tool_name: str, output: Any) -> ToolResult:
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


def truncate(text: str, max_chars: int = TOOL_OUTPUT_TRUNCATE_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n... [truncated at {max_chars} chars]"
