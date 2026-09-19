import copy
import json as _json
import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from ..core.logger import get_logger
from ..core.tracked_fields import TRACKED_FIELDS
from ..core.utils import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_OPENAI_COMPAT_BASE_URL,
    DEFAULT_TEMPERATURE,
    OPENAI_HTTP_TIMEOUT,
)
from ..tools import ToolCall
from .base import BaseProvider

logger = get_logger("providers.openai_compat")


class OpenAICompatProvider(BaseProvider):
    _include_stream_options = True

    def _get_client(self) -> AsyncOpenAI:
        return AsyncOpenAI(
            base_url=self.base_url or DEFAULT_OPENAI_COMPAT_BASE_URL,
            api_key=self.api_key or "no-key",
            timeout=OPENAI_HTTP_TIMEOUT,
            default_headers=self._extra_headers(),
        )

    def _extra_headers(self) -> dict:
        return {}

    async def stream_complete(
        self,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[dict]:
        """Produce a completion as an event stream.

        Yields dict events:
          {"type": "token", "text": str}
          {"type": "tool_calls", "calls": [ToolCall, ...]}
          {"type": "usage", "usage": dict}
          {"type": "done"}

        ``stream`` (default True) selects the upstream API mode: a streaming
        request, or one non-streaming call whose complete response is replayed
        through the same events.
        """
        merged = {**self.params, **kwargs}  # stored defaults, per-request wins
        stream_requested = merged.pop("stream", True)

        max_tokens = merged.pop("max_tokens", DEFAULT_MAX_TOKENS)
        temperature = merged.pop("temperature", DEFAULT_TEMPERATURE)
        merged.pop("preserve_thinking", None)  # handled upstream in stream.py
        merged.pop("retry", None)  # retry policy is consumed by stream.py, never sent upstream

        # Handle o1/o3 reasoning model quirks
        is_o_model = self.model.startswith("o1") or self.model.startswith("o3")

        standard_kwargs = {
            "frequency_penalty",
            "logit_bias",
            "logprobs",
            "top_logprobs",
            "max_tokens",
            "max_completion_tokens",
            "n",
            "presence_penalty",
            "response_format",
            "seed",
            "stop",
            "stream",
            "stream_options",
            "temperature",
            "top_p",
            "tools",
            "tool_choice",
            "user",
            "function_call",
            "functions",
            "parallel_tool_calls",
            "extra_headers",
            "extra_query",
            "extra_body",
            "timeout",
            "reasoning_effort",
        }

        extra_body = merged.pop("extra_body", {})

        keys_to_move = [k for k in merged.keys() if k not in standard_kwargs]
        for k in keys_to_move:
            extra_body[k] = merged.pop(k)

        request_params = {
            "model": self.model,
            "messages": messages,
            "stream": stream_requested,
            **merged,
        }

        if extra_body:
            request_params["extra_body"] = extra_body

        # stream_options is only valid (and only meaningful) on a real stream.
        if stream_requested and self._include_stream_options:
            request_params["stream_options"] = {"include_usage": True}

        if is_o_model:
            request_params["max_completion_tokens"] = max_tokens
            request_params.pop("temperature", None)
        else:
            request_params["max_tokens"] = max_tokens
            request_params["temperature"] = temperature

        if logger.isEnabledFor(logging.DEBUG):
            dump = copy.deepcopy(request_params)
            for m in dump.get("messages", []):
                c = m.get("content")
                if isinstance(c, list):
                    for p in c:
                        if p.get("type") == "image_url":
                            url = p["image_url"].get("url", "")
                            if ";" in url and "base64," in url:
                                mime, _ = url.split(";base64,", 1)
                                p["image_url"]["url"] = f"{mime};base64,<truncated>"
                        elif p.get("type") == "input_audio":
                            p["input_audio"]["data"] = "<truncated>"
            logger.debug("RAW PAYLOAD:\n%s", _json.dumps(dump, indent=2, ensure_ascii=False))

        tool_calls_acc: dict[int, dict] = {}
        nonstream_tool_calls: list[ToolCall] = []
        last_usage = None
        finish_reason: str | None = None

        async with self._get_client() as client:
            response = await client.chat.completions.create(**request_params)
            if stream_requested:
                async for chunk in response:
                    if chunk.usage:
                        last_usage = chunk.usage
                    if not chunk.choices:
                        continue
                    if getattr(chunk.choices[0], "finish_reason", None):
                        finish_reason = chunk.choices[0].finish_reason

                    delta_obj = chunk.choices[0].delta
                    delta = getattr(delta_obj, "content", None)

                    # Generic extraction for all tracked fields
                    for field_name, cfg in TRACKED_FIELDS.items():
                        value = self._extract_tracked(delta_obj, cfg)
                        if value:
                            yield {"type": "meta", "field": field_name, "value": value}

                    raw_tool_calls = getattr(delta_obj, "tool_calls", None)
                    if raw_tool_calls:
                        self._accumulate_streamed_tool_calls(tool_calls_acc, raw_tool_calls)

                    if delta:
                        yield {"type": "token", "text": delta}
            else:
                last_usage = getattr(response, "usage", None)
                choices = getattr(response, "choices", None) or []
                if choices:
                    message = choices[0].message
                    finish_reason = getattr(choices[0], "finish_reason", None)
                    for field_name, cfg in TRACKED_FIELDS.items():
                        value = self._extract_tracked(message, cfg)
                        if value:
                            yield {"type": "meta", "field": field_name, "value": value}
                    content = getattr(message, "content", None)
                    if content:
                        yield {"type": "token", "text": content}
                    raw_tool_calls = getattr(message, "tool_calls", None)
                    if raw_tool_calls:
                        nonstream_tool_calls = self._convert_tool_calls(raw_tool_calls)

        # Emit usage data if captured
        if last_usage is not None:
            yield {"type": "usage", "usage": self._usage_dict(last_usage)}

        if tool_calls_acc or nonstream_tool_calls:
            calls = (
                self._build_streamed_tool_calls(tool_calls_acc)
                if tool_calls_acc
                else nonstream_tool_calls
            )
            yield {"type": "tool_calls", "calls": calls}
        else:
            done: dict = {"type": "done"}
            if finish_reason:
                done["finish_reason"] = finish_reason
            yield done

    @staticmethod
    def _extract_tracked(obj, cfg) -> object:
        """Read one tracked field from a delta or a complete message object."""
        value = None
        for key in cfg["delta_keys"]:
            value = getattr(obj, key, None)
            if value is None and hasattr(obj, "model_extra") and obj.model_extra:
                value = obj.model_extra.get(key)
            if value:
                break
        return value

    @staticmethod
    def _accumulate_streamed_tool_calls(acc: dict[int, dict], raw_tool_calls) -> None:
        for tc in raw_tool_calls:
            idx = tc.index
            if idx not in acc:
                acc[idx] = {"id": tc.id, "name": None, "args_parts": []}
            if tc.id:
                acc[idx]["id"] = tc.id
            if tc.function:
                if tc.function.name:
                    acc[idx]["name"] = tc.function.name
                if tc.function.arguments:
                    acc[idx]["args_parts"].append(tc.function.arguments)

    @staticmethod
    def _build_streamed_tool_calls(acc: dict[int, dict]) -> list[ToolCall]:
        calls = []
        for idx in sorted(acc.keys()):
            tc = acc[idx]
            args_str = "".join(tc["args_parts"])
            arguments: dict = {}
            if args_str.strip():
                try:
                    arguments = _json.loads(args_str)
                except _json.JSONDecodeError:
                    arguments = {"_raw": args_str}
            calls.append(
                ToolCall(id=tc["id"] or "", name=tc["name"] or "", arguments=arguments)
            )
        return calls

    @staticmethod
    def _convert_tool_calls(raw_tool_calls) -> list[ToolCall]:
        """Convert complete (non-streaming) tool calls into ``ToolCall``s."""
        calls = []
        for tc in raw_tool_calls:
            fn = getattr(tc, "function", None)
            args_str = getattr(fn, "arguments", "") if fn else ""
            arguments: dict = {}
            if args_str and args_str.strip():
                try:
                    arguments = _json.loads(args_str)
                except _json.JSONDecodeError:
                    arguments = {"_raw": args_str}
            calls.append(
                ToolCall(
                    id=tc.id or "",
                    name=(getattr(fn, "name", "") or ""),
                    arguments=arguments,
                )
            )
        return calls

    @staticmethod
    def _usage_dict(last_usage) -> dict:
        usage_dict: dict = {
            "prompt_tokens": getattr(last_usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(last_usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(last_usage, "total_tokens", 0) or 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        }
        ptd = getattr(last_usage, "prompt_tokens_details", None)
        if ptd is not None:
            usage_dict["cached_tokens"] = getattr(ptd, "cached_tokens", 0) or 0
        # reasoning_tokens: check top-level field, then model_extra (OpenRouter),
        # then completion_tokens_details (OpenAI native)
        rt = getattr(last_usage, "reasoning_tokens", None)
        if rt is None and hasattr(last_usage, "model_extra") and last_usage.model_extra:
            rt = last_usage.model_extra.get("reasoning_tokens")
        if rt is None:
            ctd = getattr(last_usage, "completion_tokens_details", None)
            if ctd is not None:
                rt = getattr(ctd, "reasoning_tokens", 0) or 0
        usage_dict["reasoning_tokens"] = rt or 0
        extra = getattr(last_usage, "model_extra", None) or {}
        if "cost" in extra:
            usage_dict["cost"] = extra["cost"]
        if "cost_details" in extra:
            usage_dict["cost_details"] = extra["cost_details"]
        return usage_dict
