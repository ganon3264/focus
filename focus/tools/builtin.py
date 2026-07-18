from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

from focus.tools import ToolParam, ToolSpec


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


def read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not p.is_file():
        raise ValueError(f"Not a file: {path}")
    return p.read_text(encoding="utf-8", errors="replace")


def list_dir(path: str) -> str:
    entries = os.listdir(path)
    lines = []
    for name in sorted(entries):
        full = os.path.join(path, name)
        kind = "dir" if os.path.isdir(full) else "file"
        lines.append(f"{name}\t{kind}")
    return "\n".join(lines) if lines else "(empty directory)"


def read_image(path: str) -> tuple[str, str, str]:
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
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return (path, b64, mime)


# ── Tool registry ─────────────────────────────────────────────────────────────

ALL_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="read_file",
        description="Read the contents of a text file from the local filesystem. Returns up to ~8000 tokens of content. Use for code, config files, logs, and other text-based files.",
        params=[
            ToolParam(name="path", type="string", description="Absolute path to the file to read"),
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
        description="Read an image file and return it as a base64-encoded data URI for the model to view. Useful for inspecting screenshots, diagrams, and other visual content.",
        params=[
            ToolParam(name="path", type="string", description="Absolute path to the image file"),
        ],
        writes=False,
        handler=read_image,
    ),
    ToolSpec(
        name="execute_shell",
        description="Execute an arbitrary shell command and return its output. Can be used for any command-line operation including writing files, deleting files, running scripts, and inspecting system state. Use with caution in read-only mode.",
        params=[
            ToolParam(name="command", type="string", description="Shell command to execute"),
            ToolParam(name="timeout_s", type="integer", description="Timeout in seconds", required=False),
        ],
        writes=True,
        handler=execute_shell,
    ),
]
