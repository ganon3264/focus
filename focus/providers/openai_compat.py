import copy
import json as _json
import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from ..core.logger import get_logger
from ..core.utils import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_OPENAI_COMPAT_BASE_URL,
    DEFAULT_TEMPERATURE,
    OPENAI_HTTP_TIMEOUT,
)
from ..tools import ToolCall
from .base import BaseProvider

logger = get_logger("providers.openai")


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
        """Stream tokens from an OpenAI-compatible provider.

        Yields dict events:
          {"type": "token", "text": str}
          {"type": "tool_calls", "calls": [ToolCall, ...]}
          {"type": "done"}
        """
        merged = {**self.params, **kwargs}  # stored defaults, per-request wins

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

        request_params = {"model": self.model, "messages": messages, "stream": True, **merged}

        if extra_body:
            request_params["extra_body"] = extra_body

        if self._include_stream_options:
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

        # Accumulate tool calls across streaming chunks
        tool_calls_acc: dict[int, dict] = {}
        last_usage: dict | None = None

        async with self._get_client() as client:
            stream = await client.chat.completions.create(**request_params)
            async for chunk in stream:
                if chunk.usage:
                    last_usage = chunk.usage
                if not chunk.choices:
                    continue

                delta_obj = chunk.choices[0].delta
                delta = getattr(delta_obj, "content", None)
                reasoning = getattr(delta_obj, "reasoning_content", None) or getattr(delta_obj, "reasoning", None)

                if not reasoning and hasattr(delta_obj, "model_extra") and delta_obj.model_extra:
                    reasoning = delta_obj.model_extra.get("reasoning_content") or delta_obj.model_extra.get("reasoning")

                # Accumulate tool call deltas
                raw_tool_calls = getattr(delta_obj, "tool_calls", None)
                if raw_tool_calls:
                    for tc in raw_tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": tc.id, "name": None, "args_parts": []}
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["args_parts"].append(tc.function.arguments)

                if reasoning:
                    yield {"type": "reasoning", "text": reasoning}

                if delta:
                    yield {"type": "token", "text": delta}

        # Emit usage data if captured
        if last_usage is not None:
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
            ctd = getattr(last_usage, "completion_tokens_details", None)
            if ctd is not None:
                usage_dict["reasoning_tokens"] = getattr(ctd, "reasoning_tokens", 0) or 0
            extra = getattr(last_usage, "model_extra", None) or {}
            if "cost" in extra:
                usage_dict["cost"] = extra["cost"]
            if "cost_details" in extra:
                usage_dict["cost_details"] = extra["cost_details"]
            yield {"type": "usage", "usage": usage_dict}

        # After stream ends: emit tool_calls or done
        if tool_calls_acc:
            calls = []
            for idx in sorted(tool_calls_acc.keys()):
                tc = tool_calls_acc[idx]
                args_str = "".join(tc["args_parts"])
                arguments: dict = {}
                if args_str.strip():
                    try:
                        arguments = _json.loads(args_str)
                    except _json.JSONDecodeError:
                        arguments = {"_raw": args_str}
                calls.append(
                    ToolCall(
                        id=tc["id"] or "",
                        name=tc["name"] or "",
                        arguments=arguments,
                    )
                )
            yield {"type": "tool_calls", "calls": calls}
        else:
            yield {"type": "done"}
