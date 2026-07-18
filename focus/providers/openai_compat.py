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
    THINK_CLOSE,
    THINK_OPEN,
)
from .base import BaseProvider

logger = get_logger("providers.openai")


class OpenAICompatProvider(BaseProvider):
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
    ) -> AsyncIterator[str]:
        """Stream tokens from an OpenAI-compatible provider.

        Handles reasoning models (o1/o3), extra body passthrough,
        and wraps reasoning content in <think> tags.
        """
        merged = {**self.params, **kwargs}  # stored defaults, per-request wins

        max_tokens = merged.pop("max_tokens", DEFAULT_MAX_TOKENS)
        temperature = merged.pop("temperature", DEFAULT_TEMPERATURE)

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

        if is_o_model:
            request_params["max_completion_tokens"] = max_tokens
            # O models usually reject temperature
            request_params.pop("temperature", None)
        else:
            request_params["max_tokens"] = max_tokens
            request_params["temperature"] = temperature

        in_reasoning = False

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

        async with self._get_client() as client:
            stream = await client.chat.completions.create(**request_params)
            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta_obj = chunk.choices[0].delta
                delta = getattr(delta_obj, "content", None)
                reasoning = getattr(delta_obj, "reasoning_content", None) or getattr(delta_obj, "reasoning", None)

                if not reasoning and hasattr(delta_obj, "model_extra") and delta_obj.model_extra:
                    reasoning = delta_obj.model_extra.get("reasoning_content") or delta_obj.model_extra.get("reasoning")

                if reasoning:
                    if not in_reasoning:
                        in_reasoning = True
                        yield THINK_OPEN
                    yield reasoning

                if delta:
                    if in_reasoning:
                        in_reasoning = False
                        yield THINK_CLOSE
                    yield delta
