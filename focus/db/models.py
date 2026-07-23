from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import aiosqlite


@dataclass
class Provider:
    id: str
    name: str
    type: str
    base_url: str | None = None
    api_key: str | None = None
    model: str = ""
    params_json: str = "{}"
    created_at: str = ""

    @staticmethod
    def from_row(row: aiosqlite.Row) -> Provider:
        return Provider(**dict(row))


@dataclass
class Character:
    id: str
    name: str
    image_path: str | None = None
    card_json: str = "{}"
    created_at: str = ""
    is_deleted: int = 0

    @staticmethod
    def from_row(row: aiosqlite.Row) -> Character:
        return Character(**dict(row))


@dataclass
class CharBlock:
    id: str
    character_id: str
    name: str = ""
    content: str = ""
    role: str = "system"
    enabled: int = 1
    position: float = 0.0

    @staticmethod
    def from_row(row: aiosqlite.Row) -> CharBlock:
        return CharBlock(**dict(row))


@dataclass
class Preset:
    id: str
    name: str
    created_at: str = ""

    @staticmethod
    def from_row(row: aiosqlite.Row) -> Preset:
        return Preset(**dict(row))


@dataclass
class PresetBlock:
    id: str
    preset_id: str
    name: str = ""
    content: str = ""
    reasoning: str = ""
    role: str = "system"
    enabled: int = 1
    position: float = 0.0
    block_type: str = "text"
    injection_depth: int | None = None
    injection_order: int = 0

    @staticmethod
    def from_row(row: aiosqlite.Row) -> PresetBlock:
        return PresetBlock(**dict(row))


@dataclass
class Persona:
    id: str
    name: str
    description: str = ""
    avatar_path: str | None = None
    created_at: str = ""
    is_deleted: int = 0

    @staticmethod
    def from_row(row: aiosqlite.Row) -> Persona:
        return Persona(**dict(row))


@dataclass
class Chat:
    id: str
    title: str = "New Chat"
    character_id: str | None = None
    persona_id: str | None = None
    preset_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    is_deleted: int = 0
    tool_calls_enabled: int = 0
    tool_read_only: int = 1

    @staticmethod
    def from_row(row: aiosqlite.Row) -> Chat:
        return Chat(**dict(row))


@dataclass
class Message:
    id: str
    chat_id: str
    role: str = "user"
    position: int = 0
    active_index: int = 0
    created_at: str = ""

    @staticmethod
    def from_row(row: aiosqlite.Row) -> Message:
        return Message(**dict(row))


@dataclass
class MessageVariant:
    id: str
    message_id: str
    variant_index: int = 0
    content: str = ""
    created_at: str = ""
    model_name: str | None = None
    reasoning: str | None = None
    segments_json: str | None = None

    @staticmethod
    def from_row(row: aiosqlite.Row) -> MessageVariant:
        return MessageVariant(**dict(row))


@dataclass
class BlockImage:
    id: str
    block_id: str
    block_source: str = "preset"
    image_path: str = ""
    mime_type: str = "image/png"
    position: int = 0
    created_at: str = ""

    @staticmethod
    def from_row(row: aiosqlite.Row) -> BlockImage:
        return BlockImage(**dict(row))


@dataclass
class MessageAttachment:
    id: str
    chat_id: str
    message_id: str | None = None
    variant_id: str | None = None
    file_path: str = ""
    mime_type: str = ""
    created_at: str = ""

    @staticmethod
    def from_row(row: aiosqlite.Row) -> MessageAttachment:
        return MessageAttachment(**dict(row))


@dataclass
class Secret:
    name: str
    value: str

    @staticmethod
    def from_row(row: aiosqlite.Row) -> Secret:
        return Secret(**dict(row))


@dataclass
class Setting:
    key: str
    value: str

    @staticmethod
    def from_row(row: aiosqlite.Row) -> Setting:
        return Setting(**dict(row))


@dataclass
class ToolCall:
    id: str
    chat_id: str
    message_id: str
    variant_id: str | None = None
    tool_name: str = ""
    arguments: str = "{}"
    result: str | None = None
    is_error: int = 0
    extra_message_json: str | None = None
    created_at: str = ""

    @staticmethod
    def from_row(row: aiosqlite.Row) -> ToolCall:
        return ToolCall(**dict(row))


@dataclass
class ChatToolState:
    chat_id: str
    tool_name: str
    enabled: int = 1

    @staticmethod
    def from_row(row: aiosqlite.Row) -> ChatToolState:
        return ChatToolState(**dict(row))


@dataclass
class GenerationUsage:
    id: str
    chat_id: str
    message_id: str
    variant_id: str | None = None
    provider_id: str | None = None
    provider_type: str | None = None
    model_name: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float | None = None
    cost_details: str | None = None
    tool_iteration: int = 0
    created_at: str = ""

    @staticmethod
    def from_row(row: aiosqlite.Row) -> GenerationUsage:
        return GenerationUsage(**dict(row))
