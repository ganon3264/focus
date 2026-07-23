from __future__ import annotations

from typing import Any

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
    disabled_names: set[str] | None = None,
) -> list:
    filtered = all_tools
    if disabled_names:
        filtered = [t for t in filtered if t.name not in disabled_names]
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


def build_tool_result(call_id: str, tool_name: str, output: Any, multimodal: bool = False) -> ToolResult:  # noqa: F821
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
        mime = img.get("mime", "image/png")
        meta_parts = []
        w = img.get("width")
        h = img.get("height")
        if w and h:
            meta_parts.append(f"{w}x{h}")
        path = img.get("path")
        if path:
            meta_parts.append(path)
        meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
        return ToolResult(
            call_id=call_id,
            content=f"SUCCESS: Tool '{tool_name}' returned an image{meta}. It will be appended as a user message.",
            extra_message={
                "role": "user",
                "content": [
                    {"type": "text", "text": f"<{tool_name}>"},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64_data}"}},
                    {"type": "text", "text": f"</{tool_name}>"},
                ],
                "internal": True,
            },
        )

    return ToolResult(call_id=call_id, content=truncate(str(output)))
