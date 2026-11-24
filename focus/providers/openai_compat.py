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
from .base import BaseProvider, sdk_dump
from .config import ProviderConfig
from .profile import Capabilities, ProviderProfile

logger = get_logger("providers.openai_compat")

# Where each usage figure lives across the transports we speak. Every vendor
# picks a different spot — OpenAI nests the cache count in
# ``prompt_tokens_details``, Anthropic reports ``cache_read_input_tokens``,
# DeepSeek ``prompt_cache_hit_tokens``, and aggregators park their envelope
# beside ``usage`` instead of inside it (NanoGPT's ``x_nanogpt_cache``). Paths
# are tried in order, usage object first, so a standard field always wins and
# a new upstream shape is one line here, never an adapter override.
USAGE_FIELDS: dict[str, tuple[str, ...]] = {
    "prompt_tokens": ("prompt_tokens", "input_tokens"),
    "completion_tokens": ("completion_tokens", "output_tokens"),
    "total_tokens": ("total_tokens",),
    "cached_tokens": (
        "prompt_tokens_details.cached_tokens",
        "cache_read_input_tokens",
        "prompt_cache_hit_tokens",
        "cached_tokens",
        "x_nanogpt_cache.readTokens",
        "x_nanogpt_pricing.cacheReadInputTokens",
    ),
    "reasoning_tokens": (
        "reasoning_tokens",
        "completion_tokens_details.reasoning_tokens",
    ),
}

# Reported only when the transport sends them; absent means unknown, not zero.
OPTIONAL_USAGE_FIELDS: tuple[str, ...] = ("cost", "cost_details")


def _usage_member(obj, key: str):
    """One key off an SDK object, its ``model_extra``, or a plain dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    value = getattr(obj, key, None)
    if value is None:
        extra = getattr(obj, "model_extra", None)
        if isinstance(extra, dict):
            value = extra.get(key)
    return value


def _usage_resolve(sources, path: str):
    for source in sources:
        value = source
        for key in path.split("."):
            value = _usage_member(value, key)
            if value is None:
                break
        if value is not None:
            return value
    return None


def _usage_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class OpenAICompatProvider(BaseProvider):
    type = "openai_compat"
    # Upstream field carrying the output token cap. o-series and some
    # OpenAI-compatible vendors renamed it to ``max_completion_tokens``.
    max_tokens_param = "max_tokens"
    profile = ProviderProfile(caps=Capabilities(reasoning_formats=("openai",)))

    @classmethod
    def from_row(cls, row: dict, params: dict, config: ProviderConfig) -> "OpenAICompatProvider":
        return cls(
            base_url=row["base_url"] or DEFAULT_OPENAI_COMPAT_BASE_URL,
            api_key=row["api_key"] or "",
            model=row["model"],
            params=params,
            config=config,
        )

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
            request_params[self.max_tokens_param] = max_tokens
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
        usage_envelope: dict = {}
        finish_reason: str | None = None
        raw_chunks: list | None = [] if logger.isEnabledFor(logging.DEBUG) else None

        async with self._get_client() as client:
            response = await client.chat.completions.create(**request_params)
            if stream_requested:
                async for chunk in response:
                    extra = getattr(chunk, "model_extra", None) or {}
                    if chunk.usage:
                        last_usage = chunk.usage
                        usage_envelope = extra
                    if raw_chunks is not None:
                        raw_chunks.append(sdk_dump(chunk))
                    if extra.get("debug"):
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "Upstream debug chunk:\n%s",
                                _json.dumps(extra["debug"], indent=2, ensure_ascii=False),
                            )
                        yield {"type": "debug", "debug": extra["debug"]}
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
                usage_envelope = getattr(response, "model_extra", None) or {}
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("RAW RESPONSE:\n%s", _json.dumps(sdk_dump(response), indent=2, ensure_ascii=False))
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
        if raw_chunks:
            logger.debug("RAW RESPONSE CHUNKS:\n%s", _json.dumps(raw_chunks, indent=2, ensure_ascii=False))
        if last_usage is not None:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("RAW USAGE:\n%s", _json.dumps(sdk_dump(last_usage), indent=2, ensure_ascii=False))
            yield {"type": "usage", "usage": self._usage_dict(last_usage, usage_envelope)}

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
    def _usage_dict(last_usage, envelope: dict | None = None) -> dict:
        """Map upstream usage onto our keys; paths live in ``USAGE_FIELDS``.

        *envelope* is the chunk/response ``model_extra``, for aggregators that
        report usage figures beside ``usage`` rather than inside it.
        """
        sources = (last_usage, envelope)
        usage: dict = {}
        for field, paths in USAGE_FIELDS.items():
            value = 0
            for path in paths:
                found = _usage_resolve(sources, path)
                if found:
                    value = _usage_int(found)
                    break
            usage[field] = value
        for field in OPTIONAL_USAGE_FIELDS:
            found = _usage_resolve(sources, field)
            if found is not None:
                usage[field] = found
        return usage
