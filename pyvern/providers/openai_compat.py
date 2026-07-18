from typing import AsyncIterator

from openai import AsyncOpenAI

from .base import BaseProvider


class OpenAICompatProvider(BaseProvider):

    def _get_client(self) -> AsyncOpenAI:
        return AsyncOpenAI(
            base_url=self.base_url or "http://localhost:8080/v1",
            api_key=self.api_key or "no-key",
            timeout=120.0,
            default_headers=self._extra_headers(),
        )

    def _extra_headers(self) -> dict:
        return {}

    async def stream_complete(
        self,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[str]:
        merged = {**self.params, **kwargs}  # stored defaults, per-request wins

        # Extract max_tokens and temperature if they exist in kwargs or params, otherwise provide defaults
        max_tokens = merged.pop("max_tokens", 1024)
        temperature = merged.pop("temperature", 1.0)

        # Handle o1/o3 reasoning model quirks
        is_o_model = self.model.startswith("o1") or self.model.startswith("o3")
        
        # Standard kwargs accepted by openai.AsyncOpenAI.chat.completions.create
        STANDARD_KWARGS = {
            "frequency_penalty", "logit_bias", "logprobs", "top_logprobs",
            "max_tokens", "max_completion_tokens", "n", "presence_penalty",
            "response_format", "seed", "stop", "stream", "stream_options",
            "temperature", "top_p", "tools", "tool_choice", "user",
            "function_call", "functions", "parallel_tool_calls",
            "extra_headers", "extra_query", "extra_body", "timeout"
        }
        
        extra_body = merged.pop("extra_body", {})
        
        keys_to_move = [k for k in merged.keys() if k not in STANDARD_KWARGS]
        for k in keys_to_move:
            extra_body[k] = merged.pop(k)

        request_params = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            **merged
        }
        
        if extra_body:
            request_params["extra_body"] = extra_body
        
        if is_o_model:
            request_params["max_completion_tokens"] = max_tokens
            # O models usually reject temperature
            request_params.pop("temperature", None)
        else:
            request_params["max_tokens"] = max_tokens
            request_params["temperature"] = temperature

        self._in_reasoning = False

        async with self._get_client() as client:
            stream = await client.chat.completions.create(**request_params)
            async for chunk in stream:
                delta = getattr(chunk.choices[0].delta, "content", None)
                reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
                if reasoning:
                    if not self._in_reasoning:
                        self._in_reasoning = True
                        yield "<think>\n"
                    yield reasoning
                elif delta:
                    if self._in_reasoning:
                        self._in_reasoning = False
                        yield "\n</think>\n\n"
                    yield delta
