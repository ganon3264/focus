from dataclasses import replace

import httpx

from ..core.utils import MODEL_FETCH_HTTP_TIMEOUT
from .config import ProviderConfig
from .openai_compat import OpenAICompatProvider
from .profile import ProviderProfile

MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"


class XiaomiMiMoProvider(OpenAICompatProvider):
    """Xiaomi MiMo (OpenAI Chat Completions compatible).

    Deep thinking is toggled with the non-standard ``thinking`` field, which the
    API accepts through ``extra_body``. Thinking returns its chain of thought on
    ``reasoning_content`` and, per the vendor, that field must be echoed back on
    tool-calling assistant turns or the API rejects the request with a 400; the
    ``reasoning_message_key`` remap plus the default ``preserve_thinking`` of
    ``tool_only`` cover that. MiMo also names the output cap
    ``max_completion_tokens``.
    """

    type = "xiaomi_mimo"
    max_tokens_param = "max_completion_tokens"
    profile = ProviderProfile(
        caps=replace(
            OpenAICompatProvider.profile.caps,
            echoes_prefill=False,
            reasoning_message_key="reasoning_content",
            reasoning_formats=(),
        ),
    )

    def __init__(
        self,
        api_key: str,
        model: str,
        params: dict,
        config: ProviderConfig | None = None,
        base_url: str = MIMO_BASE_URL,
    ):
        super().__init__(base_url or MIMO_BASE_URL, api_key, model, params, config=config)

    @classmethod
    def from_row(cls, row: dict, params: dict, config: ProviderConfig) -> "XiaomiMiMoProvider":
        return cls(
            base_url=row["base_url"] or MIMO_BASE_URL,
            api_key=row["api_key"] or "",
            model=row["model"],
            params=params,
            config=config,
        )

    async def fetch_models(self) -> list[dict]:
        headers = self._build_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/models", timeout=MODEL_FETCH_HTTP_TIMEOUT, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data, list):
            return data
        return []

    async def stream_complete(self, messages: list[dict], **kwargs):
        include_reasoning = kwargs.pop("include_reasoning", None)
        kwargs.pop("reasoning_effort", None)
        kwargs.pop("preserve_thinking", None)

        extra_body = kwargs.get("extra_body", {})
        if include_reasoning is True:
            extra_body["thinking"] = {"type": "enabled"}
        elif include_reasoning is False:
            extra_body["thinking"] = {"type": "disabled"}
        kwargs["extra_body"] = extra_body

        async for chunk in super().stream_complete(messages, **kwargs):
            yield chunk
