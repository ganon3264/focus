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
    google_aistudio = "google_aistudio"
    google_vertex = "google_vertex"
    deepseek = "deepseek"
    moonshot = "moonshot"


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

class CharacterCreate(BaseModel):
    name: str
    description: str = ""
    personality: str = ""
    scenario: str = ""
    mes_example: str = ""
    first_mes: str = ""
    alternate_greetings: list[str] = []

class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    personality: Optional[str] = None
    scenario: Optional[str] = None
    mes_example: Optional[str] = None
    first_mes: Optional[str] = None
    alternate_greetings: Optional[list[str]] = None


class BlockType(str, Enum):
    text             = "text"
    chat_history     = "chat_history"
    char_description = "char_description"
    char_personality = "char_personality"
    char_blocks      = "char_blocks"
    user_persona     = "user_persona"
    variable         = "variable"

SENTINEL_TYPES = {
    BlockType.chat_history,
    BlockType.char_description,
    BlockType.char_personality,
    BlockType.char_blocks,
}


# ── Presets ──────────────────────────────────────────────────────────────────

class PresetCreate(BaseModel):
    name: str

class PresetUpdate(BaseModel):
    name: str

class PresetBlockCreate(BaseModel):
    name: str
    content: str = ""
    role: Role = Role.system
    enabled: bool = True
    block_type: BlockType = BlockType.text
    injection_depth: Optional[int] = None
    injection_order: int = 0

class PresetBlockBulkUpdate(BaseModel):
    blocks: list[dict[str, Any]]


# ── Chats ────────────────────────────────────────────────────────────────────

class ChatCreate(BaseModel):
    character_id: Optional[str] = None
    persona_id: Optional[str] = None
    preset_id: Optional[str] = None
    title: Optional[str] = None

class MessageEdit(BaseModel):
    content: str
    attachment_ids: list[str] = Field(default_factory=list)

class SwipeDirection(str, Enum):
    prev = "prev"
    next = "next"

class SwipeRequest(BaseModel):
    direction: SwipeDirection = SwipeDirection.next


# ── Stream ───────────────────────────────────────────────────────────────────

class StreamRequest(BaseModel):
    chat_id: str
    provider_id: str = ""
    user_message: str = ""
    # Override generation params per-request (falls back to provider defaults)
    samplers: dict[str, Any] = Field(default_factory=dict)
    # For swipe/regen: regenerate the last assistant turn instead of appending
    regenerate: bool = False
    # Attachment IDs to bind to the new user message
    attachment_ids: list[str] = Field(default_factory=list)

class ItemizerRequest(BaseModel):
    chat_id: str
    user_message: str = ""
    attachment_ids: list[str] = Field(default_factory=list)
    regenerate: bool = False


# ── Import / Export ───────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    characters: list[str] = Field(default_factory=list)
    personas: list[str] = Field(default_factory=list)
    presets: list[str] = Field(default_factory=list)
    chats: list[str] = Field(default_factory=list)
    include_providers: bool = False
    include_secrets: bool = False
