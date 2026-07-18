import base64
import logging

from google.genai import types

from ..core.logger import get_logger
from ..core.utils import THINK_CLOSE, THINK_OPEN, THOUGHT_SIGNATURE_CLOSE, THOUGHT_SIGNATURE_OPEN
from .base import BaseProvider

logger = get_logger("providers.google_base")

_HARM_CATEGORIES = [
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
    "HARM_CATEGORY_CIVIC_INTEGRITY",
    "HARM_CATEGORY_IMAGE_HATE",
    "HARM_CATEGORY_IMAGE_DANGEROUS_CONTENT",
    "HARM_CATEGORY_IMAGE_HARASSMENT",
    "HARM_CATEGORY_IMAGE_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_JAILBREAK",
]

VERTEX_SAFETY_OFF = [types.SafetySetting(category=c, threshold="OFF") for c in _HARM_CATEGORIES]

AI_STUDIO_SAFETY_OFF = [
    types.SafetySetting(category=c, threshold=types.HarmBlockThreshold.BLOCK_NONE)
    for c in [
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    ]
]


class GoogleProviderBase(BaseProvider):
    supports_prefill = False
    supports_tools = False

    def __init__(self, api_key: str, model: str, params: dict):
        super().__init__("", api_key, model, params)

    @staticmethod
    def _extract_text(content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
        return str(content)

    @staticmethod
    def _build_parts(content, reasoning=None, thought_signature_b64=None):
        parts = []
        if reasoning:
            parts.append(types.Part(text=reasoning, thought=True))

        sig_bytes = base64.b64decode(thought_signature_b64) if thought_signature_b64 else None

        if isinstance(content, str):
            parts.append(types.Part(text=content, thought_signature=sig_bytes))
            return parts

        if isinstance(content, list):
            sig_attached = False
            for part in content:
                ptype = part.get("type")
                if ptype == "text":
                    kwargs = {"text": part.get("text", "")}
                    if sig_bytes and not sig_attached:
                        kwargs["thought_signature"] = sig_bytes
                        sig_attached = True
                    parts.append(types.Part(**kwargs))
                elif ptype == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if url.startswith("data:"):
                        mime_b64 = url[5:]
                        if ";base64," in mime_b64:
                            mime, b64 = mime_b64.split(";base64,", 1)
                            raw_bytes = base64.b64decode(b64)
                            parts.append(types.Part.from_bytes(data=raw_bytes, mime_type=mime))
            if sig_bytes and not sig_attached:
                parts.append(types.Part(thought_signature=sig_bytes))
        return parts

    def _find_last_assistant_with_signature(self, messages: list[dict]) -> int | None:
        last_assistant_idx = None
        for i, m in enumerate(messages):
            if m.get("role") == "assistant" and m.get("thought_signature"):
                last_assistant_idx = i
        return last_assistant_idx

    def _build_contents(self, messages: list[dict], merged: dict, last_assistant_idx: int | None, include_sig: bool):
        system_instruction = None
        contents = []
        for msg_idx, msg in enumerate(messages):
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                extracted = self._extract_text(content)
                if system_instruction is None:
                    system_instruction = extracted
                else:
                    system_instruction += "\n\n" + extracted
            elif role == "user":
                contents.append(types.Content(role="user", parts=self._build_parts(content)))
            elif role == "assistant":
                reasoning = msg.get("reasoning") if merged.get("send_reasoning_history", True) else None
                thought_sig = (
                    msg.get("thought_signature")
                    if (include_sig and msg_idx == last_assistant_idx and merged.get("send_reasoning_history", True))
                    else None
                )
                contents.append(types.Content(role="model", parts=self._build_parts(content, reasoning, thought_sig)))
        return system_instruction, contents

    async def _do_stream(self, contents, config):
        if logger.isEnabledFor(logging.DEBUG):
            try:
                import json as _json

                contents_dump = [c.model_dump(exclude_none=True) for c in contents]
                config_dump = config.model_dump(exclude_none=True) if config else {}

                def _sanitize(o):
                    if isinstance(o, dict):
                        return {k: _sanitize(v) for k, v in o.items()}
                    if isinstance(o, list):
                        return [_sanitize(v) for v in o]
                    if isinstance(o, bytes):
                        return f"<bytes len={len(o)}>"
                    return o

                contents_dump = _sanitize(contents_dump)
                config_dump = _sanitize(config_dump)
                logger.debug(
                    "GOOGLE RAW PAYLOAD:\nmodel=%s\ncontents=\n%s\nconfig=\n%s",
                    self.model,
                    _json.dumps(contents_dump, indent=2, ensure_ascii=False),
                    _json.dumps(config_dump, indent=2, ensure_ascii=False),
                )
            except Exception:
                logger.debug("Failed to serialize debug payload", exc_info=True)

        stream = await self.client.aio.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=config,
        )
        in_reasoning = False
        thought_signature_b64 = None

        async for chunk in stream:
            if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                if chunk.text:
                    yield {"type": "token", "text": chunk.text}
                continue

            for part in chunk.candidates[0].content.parts:
                if hasattr(part, "thought_signature") and part.thought_signature:
                    thought_signature_b64 = base64.b64encode(part.thought_signature).decode("utf-8")

                is_thought = getattr(part, "thought", False) or (part.text and part.text.startswith("THOUGHT:"))

                if is_thought:
                    if not in_reasoning:
                        in_reasoning = True
                        yield {"type": "token", "text": THINK_OPEN}

                    clean_text = part.text.replace("THOUGTH:", "") if part.text else ""

                    if clean_text:
                        yield {"type": "token", "text": clean_text}
                else:
                    if in_reasoning:
                        in_reasoning = False
                        yield {"type": "token", "text": THINK_CLOSE}

                    if part.text:
                        yield {"type": "token", "text": part.text}

        if in_reasoning:
            in_reasoning = False
            yield {"type": "token", "text": THINK_CLOSE}

        if thought_signature_b64:
            yield {"type": "token", "text": f"\n{THOUGHT_SIGNATURE_OPEN}{thought_signature_b64}{THOUGHT_SIGNATURE_CLOSE}"}

    async def stream_complete(self, messages: list[dict], **kwargs):
        """Stream tokens from a Google Gemini model.

        Builds contents with thought signatures, streams via _do_stream,
        and retries once without thought_signature on failure.
        """
        merged = {**self.params, **kwargs}
        last_assistant_idx = self._find_last_assistant_with_signature(messages)
        system_instruction, contents = self._build_contents(messages, merged, last_assistant_idx, True)

        config = self._build_config(merged, system_instruction)

        try:
            async for chunk in self._do_stream(contents, config):
                yield chunk
        except Exception:
            if last_assistant_idx is not None:
                logger.debug("First stream attempt failed, retrying without thought_signature", exc_info=True)
                _, contents_retry = self._build_contents(messages, merged, last_assistant_idx, False)
                async for chunk in self._do_stream(contents_retry, config):
                    yield chunk
            else:
                raise

        yield {"type": "done"}

    def _build_config(self, merged: dict, system_instruction: str | None) -> types.GenerateContentConfig:
        raise NotImplementedError

    @staticmethod
    def _apply_thinking_config(config: dict, model: str, include_reasoning: bool | None, reasoning_effort: str | None):
        if include_reasoning is False:
            config["thinking_config"] = types.ThinkingConfig(include_thoughts=False, thinking_level="minimal")
        elif include_reasoning or "gemini-3.1" in model or "gemini-2.0-flash-thinking" in model:
            config.pop("temperature", None)
            thinking_kwargs = {"include_thoughts": True}
            if reasoning_effort:
                thinking_kwargs["thinking_level"] = reasoning_effort
            config["thinking_config"] = types.ThinkingConfig(**thinking_kwargs)
