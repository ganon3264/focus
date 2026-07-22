from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .helpers import MAX_TOOL_ITERATIONS, active_tools, build_tool_result, extract_image_url


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
    multimodal: bool = False


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
