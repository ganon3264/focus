from __future__ import annotations

import base64
import os
import subprocess
from io import BytesIO
from pathlib import Path

from PIL import Image

from focus.prompt_chain import _ensure_compressed_sync
from focus.tools import ToolParam, ToolSpec
from focus.tools.external import load_external_tools
from focus.tools.helpers import TOOL_OUTPUT_TRUNCATE_CHARS


def execute_shell(command: str, timeout_s: int = 10) -> str:
    result = subprocess.run(
        ["/bin/sh", "-c", command],
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    output = result.stdout or ""
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    if result.returncode != 0:
        output = output or f"(exit code {result.returncode})"
    return output


def read_file(path: str, lines: int | None = None) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not p.is_file():
        raise ValueError(f"Not a file: {path}")
    if lines is not None:
        with p.open(encoding="utf-8", errors="replace") as f:
            return "".join(f.readline() for _ in range(lines))
    return p.read_text(encoding="utf-8", errors="replace")


def list_dir(path: str) -> str:
    entries = os.listdir(path)
    lines = []
    for name in sorted(entries):
        full = os.path.join(path, name)
        kind = "dir" if os.path.isdir(full) else "file"
        lines.append(f"{name}\t{kind}")
    return "\n".join(lines) if lines else "(empty directory)"


def read_image(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    suffix = p.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_map.get(suffix, "image/png")
    compressed_path, out_mime = _ensure_compressed_sync(path, mime)
    data = compressed_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    with Image.open(BytesIO(data)) as img:
        w, h = img.size
    return {"image": {"base64": b64, "mime": out_mime, "path": path, "width": w, "height": h}}


# ── Tool registry ─────────────────────────────────────────────────────────────

BUILTIN_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="read_file",
        description=f"Read the contents of a text file from the local filesystem. "
                    f"Truncated if longer than {TOOL_OUTPUT_TRUNCATE_CHARS} chars. "
                    f"Optionally read only the first N lines.",
        params=[
            ToolParam(name="path", type="string", description="Absolute path to the file to read"),
            ToolParam(name="lines", type="integer",
                      description="Number of lines to read from the start of the file (optional)",
                      required=False),
        ],
        writes=False,
        handler=read_file,
    ),
    ToolSpec(
        name="list_dir",
        description="List files and directories at a given path. Returns names with a type indicator (file/dir).",
        params=[
            ToolParam(name="path", type="string", description="Absolute path to the directory to list"),
        ],
        writes=False,
        handler=list_dir,
    ),
    ToolSpec(
        name="read_image",
        description="Read an image file and return it as a base64-encoded data URI for the model to view.",
        params=[
            ToolParam(name="path", type="string", description="Absolute path to the image file"),
        ],
        writes=False,
        multimodal=True,
        handler=read_image,
    ),
    ToolSpec(
        name="execute_shell",
        description="Execute an arbitrary shell command and return its output.",
        params=[
            ToolParam(name="command", type="string", description="Shell command to execute"),
            ToolParam(name="timeout_s", type="integer", description="Timeout in seconds", required=False),
        ],
        writes=True,
        handler=execute_shell,
    ),
]

_tool_cache: list[ToolSpec] | None = None


def get_all_tools() -> list[ToolSpec]:
    global _tool_cache
    if _tool_cache is None:
        _tool_cache = BUILTIN_TOOLS + load_external_tools()
    return list(_tool_cache)


def reload_tools() -> list[ToolSpec]:
    global _tool_cache
    _tool_cache = BUILTIN_TOOLS + load_external_tools()
    return list(_tool_cache)
