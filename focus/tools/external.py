from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

from focus.core.paths import TOOLS_DIR
from focus.tools import ToolParam, ToolSpec

logger = logging.getLogger("focus.tools.external")

EXTERNAL_TOOLS_DIR = TOOLS_DIR

ALLOWED_PARAM_TYPES = {"string", "integer", "boolean", "number"}


class ToolParamDef(BaseModel):
    name: str
    type: str
    description: str = ""
    required: bool = True

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in ALLOWED_PARAM_TYPES:
            raise ValueError(f"type must be one of {ALLOWED_PARAM_TYPES}")
        return v


class ExternalToolConfig(BaseModel):
    name: str
    description: str
    command: str | list[str]
    timeout: int = 30
    writes: bool = False
    multimodal: bool = False
    params: list[ToolParamDef] = []


def _parse_command(command: str | list[str]) -> list[str]:
    if isinstance(command, str):
        return shlex.split(command)
    return command


def _run_external_tool(command: list[str], params: dict[str, Any], timeout: int = 30) -> Any:
    result = subprocess.run(
        command,
        input=json.dumps(params),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"exit code {result.returncode}")
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout
    if isinstance(response, dict):
        if response.get("error"):
            raise RuntimeError(response["error"])
        if "image" in response:
            return response
        if "output" in response:
            return response["output"]
    return result.stdout


def _load_single_tool(path: Path) -> ToolSpec:
    config = ExternalToolConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))

    command = _parse_command(config.command)
    params = [
        ToolParam(
            name=p.name,
            type=p.type,
            description=p.description,
            required=p.required,
        )
        for p in config.params
    ]

    def handler(**kwargs: Any) -> Any:
        return _run_external_tool(command, kwargs, timeout=config.timeout)

    return ToolSpec(
        name=config.name,
        description=config.description,
        params=params,
        writes=config.writes,
        multimodal=config.multimodal,
        handler=handler,
    )


def load_external_tools(tools_dir: str | Path | None = None) -> list[ToolSpec]:
    if tools_dir is None:
        d = EXTERNAL_TOOLS_DIR
    else:
        d = Path(tools_dir)

    if not d.is_dir():
        return []

    tools: list[ToolSpec] = []
    MAX_DEPTH = 2
    for f in sorted(d.rglob("*.json")):
        if not f.is_file():
            continue
        rel = f.relative_to(d)
        if len(rel.parents) >= MAX_DEPTH:
            continue
        if any(p.name.startswith(".") for p in rel.parents):
            continue
        try:
            tools.append(_load_single_tool(f))
        except Exception as exc:
            logger.warning("Skipping external tool %s: %s", f.name, exc)
    return tools
