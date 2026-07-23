from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .helpers import (
    MAX_TOOL_ITERATIONS as MAX_TOOL_ITERATIONS,
)
from .helpers import (
    active_tools as active_tools,
)
from .helpers import (
    build_tool_result as build_tool_result,
)
from .helpers import (
    extract_image_url as extract_image_url,
)


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
