from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Role(StrEnum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"


class ProviderType(StrEnum):
    openai_compat = "openai_compat"
    openrouter = "openrouter"
    google_aistudio = "google_aistudio"
    google_vertex = "google_vertex"
    deepseek = "deepseek"
    moonshot = "moonshot"


class ProviderCreate(BaseModel):
    name: str
    type: ProviderType
    base_url: str | None = None
    api_key: str | None = None
    model: str
    params: dict[str, Any] = Field(default_factory=dict)


class ProviderOut(BaseModel):
    id: str
    name: str
    type: str
    base_url: str | None
    model: str
    created_at: str


class CharBlockCreate(BaseModel):
    name: str
    content: str = ""
    role: Role = Role.system
    enabled: bool = True
    position: float = 0.0


class CharBlockUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    role: Role | None = None
    enabled: bool | None = None
    position: float | None = None


class CharacterCreate(BaseModel):
    name: str
    description: str = ""
    personality: str = ""
    scenario: str = ""
    mes_example: str = ""
    first_mes: str = ""
    alternate_greetings: list[str] = []


class CharacterUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    personality: str | None = None
    scenario: str | None = None
    mes_example: str | None = None
    first_mes: str | None = None
    alternate_greetings: list[str] | None = None


class BlockType(StrEnum):
    text = "text"
    chat_history = "chat_history"
    char_description = "char_description"
    char_personality = "char_personality"
    char_blocks = "char_blocks"
    user_persona = "user_persona"
    variable = "variable"


SENTINEL_TYPES = {
    BlockType.chat_history,
    BlockType.char_description,
    BlockType.char_personality,
    BlockType.char_blocks,
}


class PresetUpdate(BaseModel):
    name: str


class PresetBlockCreate(BaseModel):
    name: str
    content: str = ""
    reasoning: str = ""
    role: Role = Role.system
    enabled: bool = True
    block_type: BlockType = BlockType.text
    injection_depth: int | None = None
    injection_order: int = 0


class PresetBlockBulkUpdate(BaseModel):
    blocks: list[dict[str, Any]]


class ChatCreate(BaseModel):
    character_id: str | None = None
    persona_id: str | None = None
    preset_id: str | None = None
    title: str | None = None


class MessageEdit(BaseModel):
    content: str
    reasoning: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)


class StreamRequest(BaseModel):
    chat_id: str
    provider_id: str = ""
    user_message: str = ""
    # Override generation params per-request (falls back to provider defaults)
    samplers: dict[str, Any] = Field(default_factory=dict)
    # For swipe/regen: regenerate the last assistant turn instead of appending
    regenerate: bool = False
    # For Continue: prefill the assistant response with existing partial text
    continue_text: str | None = None
    continue_reasoning: str | None = None
    # Attachment IDs to bind to the new user message
    attachment_ids: list[str] = Field(default_factory=list)
    # Tool calling configuration
    tools_enabled: bool = False
    tool_read_only: bool = True


class ItemizerRequest(BaseModel):
    chat_id: str
    user_message: str = ""
    attachment_ids: list[str] = Field(default_factory=list)
    regenerate: bool = False


class SettingsUpdate(BaseModel):
    key: str
    value: str


class ActiveProviderUpdate(BaseModel):
    provider_id: str | None = None
    provider_type: str | None = None


class ExportRequest(BaseModel):
    characters: list[str] = Field(default_factory=list)
    personas: list[str] = Field(default_factory=list)
    presets: list[str] = Field(default_factory=list)
    chats: list[str] = Field(default_factory=list)
    include_providers: bool = False
    include_secrets: bool = False
