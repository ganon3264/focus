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
        max_tokens: int = 1024,
        temperature: float = 1.0,
        **kwargs,
    ) -> AsyncIterator[str]:
        merged = {**self.params, **kwargs}  # stored defaults, per-request wins

        async with self._get_client() as client:
            stream = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                **merged,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
