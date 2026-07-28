import base64
import json
import logging

from google.genai import types

from ..core.logger import get_logger
from ..tools import ToolCall
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
    supports_tools = True

    def __init__(self, api_key: str, model: str, params: dict):
        super().__init__("", api_key, model, params)
        self._pending_thought_signatures: dict[str, bytes] = {}

    @staticmethod
    def _extract_text(content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
        return str(content)

    @staticmethod
    def _to_google_tools(openai_tools: list[dict]) -> list[types.Tool] | None:
        """Convert OpenAI-compatible tool list to Google SDK Tool list.

        OpenAI format from ``to_provider_tools()``::

            [{"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}]

        Pydantic v2 auto-coerces the JSON Schema ``parameters`` dict into
        ``types.Schema`` objects, including enum conversion (``"string"`` → ``Type.STRING``).
        """
        if not openai_tools:
            return None
        declarations = []
        for tool in openai_tools:
            fn = tool["function"]
            declarations.append(
                types.FunctionDeclaration(
                    name=fn.get("name", ""),
                    description=fn.get("description", ""),
                    parameters=fn.get("parameters"),
                )
            )
        return [types.Tool(function_declarations=declarations)]

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
        # Track function names from assistant tool_calls so we can look them up
        # when processing subsequent tool-role messages.
        pending_fc_names: dict[str, str] = {}
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
                parts = self._build_parts(content, reasoning, thought_sig)
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    for tc in tool_calls:
                        fc_id = tc["id"]
                        fc_name = tc["function"]["name"]
                        fc_args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                        part_kwargs = {
                            "function_call": types.FunctionCall(
                                id=fc_id, name=fc_name, args=fc_args,
                            ),
                        }
                        ts = tc.get("_thought_signature")
                        if ts:
                            part_kwargs["thought_signature"] = ts
                        parts.append(types.Part(**part_kwargs))
                        pending_fc_names[fc_id] = fc_name
                contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                fc_name = pending_fc_names.get(tool_call_id, "")
                result_text = self._extract_text(content)
                parts = [
                    types.Part(function_response=types.FunctionResponse(
                        id=tool_call_id or None,
                        name=fc_name,
                        response={"result": result_text},
                    ))
                ]
                contents.append(types.Content(role="user", parts=parts))
        return system_instruction, contents

    def _inject_pending_signatures(self, messages: list[dict]) -> None:
        """Inject captured thought_signatures into tool_calls dicts before
        ``_build_contents`` so that function_call parts carry the signature
        the Gemini API requires on multi-turn tool requests."""
        if not self._pending_thought_signatures:
            return
        for msg in messages:
            tcs = msg.get("tool_calls")
            if not tcs:
                continue
            for tc in tcs:
                ts = self._pending_thought_signatures.pop(tc["id"], None)
                if ts:
                    tc["_thought_signature"] = ts
        self._pending_thought_signatures.clear()

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

        # Accumulate function calls across streaming chunks
        function_calls_acc: dict[str, dict] = {}
        last_usage = None
        async for chunk in stream:
            if chunk.usage_metadata is not None:
                last_usage = chunk.usage_metadata

            if not chunk.candidates or not chunk.candidates[0].content:
                continue

            parts = chunk.candidates[0].content.parts
            if not parts:
                continue

            for part in parts:
                if part.function_call:
                    fc = part.function_call
                    fc_id = fc.id or ""
                    if fc_id not in function_calls_acc:
                        function_calls_acc[fc_id] = {"id": fc_id, "name": fc.name or "", "args": {}}
                    if fc_id:
                        if fc.name:
                            function_calls_acc[fc_id]["name"] = fc.name
                        if fc.args:
                            function_calls_acc[fc_id]["args"].update(fc.args)
                        if part.thought_signature:
                            self._pending_thought_signatures[fc_id] = part.thought_signature
                if part.text:
                    if part.thought:
                        yield {"type": "meta", "field": "reasoning", "value": part.text}
                    else:
                        yield {"type": "token", "text": part.text}

        if function_calls_acc:
            calls = [
                ToolCall(id=fc["id"], name=fc["name"], arguments=fc["args"])
                for fc in function_calls_acc.values()
            ]
            yield {"type": "tool_calls", "calls": calls}

        if last_usage is not None:
            yield {"type": "usage", "usage": {
                "prompt_tokens": getattr(last_usage, "prompt_token_count", 0) or 0,
                "completion_tokens": getattr(last_usage, "candidates_token_count", 0) or 0,
                "total_tokens": getattr(last_usage, "total_token_count", 0) or 0,
                "cached_tokens": getattr(last_usage, "cached_content_token_count", 0) or 0,
            }}

    async def stream_complete(self, messages: list[dict], **kwargs):
        """Stream tokens from a Google Gemini model.

        Builds contents with thought signatures, streams via _do_stream,
        and retries once without thought_signature on failure.
        """
        merged = {**self.params, **kwargs}
        last_assistant_idx = self._find_last_assistant_with_signature(messages)

        # Convert tools from OpenAI-compatible payload to Google SDK format
        google_tools = self._to_google_tools(merged.pop("tools", None))
        merged.pop("tool_choice", None)  # unused by Google SDK

        # Stamp thought_signatures from the previous streaming round onto
        # tool_calls dicts so the Gemini API doesn't reject them.
        self._inject_pending_signatures(messages)

        system_instruction, contents = self._build_contents(messages, merged, last_assistant_idx, True)

        config = self._build_config(merged, system_instruction, google_tools=google_tools)

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

    def _build_config(self, merged: dict, system_instruction: str | None, **kwargs) -> types.GenerateContentConfig:
        raise NotImplementedError

    @staticmethod
    def _apply_thinking_config(config: dict, model: str, include_reasoning: bool | None, reasoning_effort: str | None):
        if isinstance(include_reasoning, str):
            include_reasoning = include_reasoning.lower() in ("true", "1", "yes")
        if include_reasoning is False:
            config["thinking_config"] = types.ThinkingConfig(include_thoughts=False, thinking_level="minimal")
            return
        if include_reasoning is True or include_reasoning is None:
            config.pop("temperature", None)
            kwargs = {"include_thoughts": True}
            if reasoning_effort:
                kwargs["thinking_level"] = reasoning_effort
            config["thinking_config"] = types.ThinkingConfig(**kwargs)
