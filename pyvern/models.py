from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum


class Role(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class ProviderType(str, Enum):
    openai_compat = "openai_compat"
    openrouter = "openrouter"


# ── Providers ────────────────────────────────────────────────────────────────

class ProviderCreate(BaseModel):
    name: str
    type: ProviderType
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: str
    params: dict[str, Any] = Field(default_factory=dict)

class ProviderOut(BaseModel):
    id: str
    name: str
    type: str
    base_url: Optional[str]
    model: str
    created_at: str


# ── Characters ───────────────────────────────────────────────────────────────

class CharBlockCreate(BaseModel):
    name: str
    content: str = ""
    role: Role = Role.system
    enabled: bool = True
    position: float = 0.0

class CharBlockUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    role: Optional[Role] = None
    enabled: Optional[bool] = None
    position: Optional[float] = None

class CharacterCard(BaseModel):
    name: str = "Unknown"
    description: str = ""
    personality: str = ""
    scenario: str = ""
    mes_example: str = ""
    first_mes: str = ""


# ── Presets ──────────────────────────────────────────────────────────────────

class PresetCreate(BaseModel):
    name: str

class PresetBlockCreate(BaseModel):
    name: str
    content: str = ""
    role: Role = Role.system
    enabled: bool = True
    position: float = 0.0
    is_sentinel: bool = False
    source: str = "preset"
    character_id: Optional[str] = None

class PresetBlockBulkUpdate(BaseModel):
    blocks: list[dict[str, Any]]


# ── Chats ────────────────────────────────────────────────────────────────────

class ChatCreate(BaseModel):
    character_id: Optional[str] = None
    preset_id: Optional[str] = None
    title: Optional[str] = None

class MessageEdit(BaseModel):
    content: str

class SwipeDirection(str, Enum):
    prev = "prev"
    next = "next"

class SwipeRequest(BaseModel):
    direction: SwipeDirection = SwipeDirection.next


# ── Stream ───────────────────────────────────────────────────────────────────

class StreamRequest(BaseModel):
    chat_id: str
    provider_id: str
    user_message: str
    # Override generation params per-request (falls back to provider defaults)
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    # For swipe/regen: regenerate the last assistant turn instead of appending
    regenerate: bool = False
