from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

ALLOWED_PARAM_TYPES = {"string", "integer", "boolean", "number", "array"}
ALLOWED_ROLES = {"assistant", "user"}
ALLOWED_NEEDS = {"message", "transcript"}
TRIGGER_EVENTS = {"manual", "generation_start", "generation_end", "edit", "swipe"}
_ALLOWED_LOG_LEVELS = {"info", "success", "warning", "error"}


class ExtensionParam(BaseModel):
    """A user-config form field, declared in the extension spec's ``params``."""

    name: str
    type: str
    description: str = ""
    default: Any = None
    required: bool = False
    enum: list[str] | None = None
    items: dict[str, Any] | None = None

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in ALLOWED_PARAM_TYPES:
            raise ValueError(f"type must be one of {ALLOWED_PARAM_TYPES}")
        return v


class ExtensionSpec(BaseModel):
    """The ``extensions/*.json`` contract."""

    name: str
    description: str
    command: str | list[str]
    timeout: int = 30
    category: str = "General"
    icon: str = ""
    roles: list[str] = ["assistant"]
    needs: list[str] = ["message"]
    triggers: list[str] = ["manual"]
    secrets: list[str] = []
    params: list[ExtensionParam] = []

    @field_validator("roles")
    @classmethod
    def _validate_roles(cls, v: list[str]) -> list[str]:
        for r in v:
            if r not in ALLOWED_ROLES:
                raise ValueError(f"role must be one of {ALLOWED_ROLES}")
        return v

    @field_validator("needs")
    @classmethod
    def _validate_needs(cls, v: list[str]) -> list[str]:
        for n in v:
            if n not in ALLOWED_NEEDS:
                raise ValueError(f"needs must be one of {ALLOWED_NEEDS}")
        return v

    @field_validator("triggers")
    @classmethod
    def _validate_triggers(cls, v: list[str]) -> list[str]:
        for t in v:
            if t not in TRIGGER_EVENTS:
                raise ValueError(f"trigger must be one of {TRIGGER_EVENTS}")
        return v


class ExtensionAction(BaseModel):
    """A single side-effect the extension asks Focus to perform."""

    type: str  # "create_swipe"
    message_id: str | None = None
    content: str | None = None
    reasoning: str | None = None
    segments: list[dict[str, Any]] | None = None


class ExtensionFile(BaseModel):
    """A file the extension returns to be attached to the target message."""

    name: str
    data: str  # base64
    mime: str = "application/octet-stream"


class ExtensionLog(BaseModel):
    level: str = "info"
    message: str

    @field_validator("level")
    @classmethod
    def _validate_level(cls, v: str) -> str:
        if v not in _ALLOWED_LOG_LEVELS:
            raise ValueError(f"level must be one of {_ALLOWED_LOG_LEVELS}")
        return v


class ExtensionResult(BaseModel):
    """The parsed ``stdout`` of a run — what Focus executes."""

    status: str = "done"
    error: str | None = None
    content: str | None = None
    action: ExtensionAction | None = None
    files: list[ExtensionFile] = Field(default_factory=list)
    logs: list[ExtensionLog] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        if v not in ("done", "error"):
            raise ValueError("status must be 'done' or 'error'")
        return v
