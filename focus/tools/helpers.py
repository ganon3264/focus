from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from typing import Any

from PIL import Image

from focus.core.media import compress_image, image_format_var, mime_for

TOOL_OUTPUT_TRUNCATE_CHARS = 32000
MAX_TOOL_ITERATIONS = 10


def truncate(text: str, max_chars: int = TOOL_OUTPUT_TRUNCATE_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n... [truncated at {max_chars} chars]"


def active_tools(
    all_tools: list,
    read_only: bool,
    disable_multimodal: bool = False,
    enabled_names: set[str] | None = None,
) -> list:
    if enabled_names is not None:
        filtered = [t for t in all_tools if t.name in enabled_names]
    else:
        filtered = list(all_tools)
    filtered = [t for t in filtered if not (read_only and t.writes)]
    if disable_multimodal:
        filtered = [t for t in filtered if not t.multimodal]
    return filtered


def extract_image_url(result) -> str | None:
    extra = getattr(result, "extra_message", None)
    if not extra:
        return None
    content = extra.get("content", [])
    if not isinstance(content, list):
        return None
    for part in content:
        if isinstance(part, dict) and part.get("type") == "image_url":
            url = part.get("image_url", {}).get("url")
            if url:
                return url
    return None


async def build_tool_result(call_id: str, tool_name: str, output: Any, multimodal: bool = False) -> ToolResult:  # noqa: F821
    from focus.tools import ToolResult  # lazy to avoid circular import

    if isinstance(output, dict) and "image" in output:
        if not multimodal:
            return ToolResult(
                call_id=call_id,
                content=truncate(str(output)),
            )
        img = output["image"]
        if not isinstance(img, dict) or not img.get("base64"):
            return ToolResult(
                call_id=call_id,
                content="Tool returned image key without base64 data.",
                is_error=True,
            )
        b64_data = img["base64"]
        raw_mime = img.get("mime", "image/png")
        try:
            raw = base64.b64decode(b64_data)
        except Exception:
            return ToolResult(
                call_id=call_id,
                content="Tool returned invalid base64 image data.",
                is_error=True,
            )
        try:
            fmt = image_format_var.get()
            converted = await asyncio.to_thread(compress_image, raw, fmt)
        except Exception as e:
            return ToolResult(
                call_id=call_id,
                content=f"Tool returned an image that could not be processed: {e}",
                is_error=True,
            )
        out_mime = mime_for(fmt)
        with Image.open(BytesIO(converted)) as conv_img:
            w, h = conv_img.size
        meta_parts = [f"{w}x{h}"]
        path = img.get("path")
        if path:
            meta_parts.append(path)
        meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
        converted_url = f"data:{out_mime};base64,{base64.b64encode(converted).decode('ascii')}"
        return ToolResult(
            call_id=call_id,
            content=f"SUCCESS: Tool '{tool_name}' returned an image{meta}. It will be appended as a user message.",
            extra_message={
                "role": "user",
                "content": [
                    {"type": "text", "text": f"<{tool_name}>"},
                    {"type": "image_url", "image_url": {"url": converted_url}},
                    {"type": "text", "text": f"</{tool_name}>"},
                ],
                "internal": True,
            },
            image_data_url=f"data:{raw_mime};base64,{b64_data}",
        )

    return ToolResult(call_id=call_id, content=truncate(str(output)))
