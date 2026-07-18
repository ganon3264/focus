from abc import ABC, abstractmethod
from typing import AsyncIterator

import httpx

from ..utils import MODEL_FETCH_HTTP_TIMEOUT


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

    async def fetch_models(self) -> list[dict]:
        """Fetch available models from this provider.

        Returns a list of dicts with at least an ``id`` key.
        The default implementation hits ``GET {base_url}/models`` with
        ``_build_headers()``.  Override for providers with a different API.
        """
        url = f"{self.base_url}/models"
        headers = self._build_headers()
        extra = getattr(self, "_extra_headers", None)
        if extra:
            headers.update(extra())
        if self.api_key and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=MODEL_FETCH_HTTP_TIMEOUT, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return data["data"]
        if isinstance(data, list):
            return data
        return []

    @abstractmethod
    async def stream_complete(
        self,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[str]: ...
