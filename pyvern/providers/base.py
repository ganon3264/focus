from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseProvider(ABC):
    def __init__(self, base_url: str, api_key: str, model: str, params: dict):
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.api_key = api_key or ""
        self.model = model
        self.params = params  # stored defaults (top_p, rep_pen, etc.)

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @abstractmethod
    async def stream_complete(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 1.0,
        **kwargs,
    ) -> AsyncIterator[str]: ...
