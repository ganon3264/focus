import httpx

from ..core.logger import get_logger
from ..core.utils import MODEL_FETCH_HTTP_TIMEOUT
from .openai_compat import OpenAICompatProvider

logger = get_logger("providers.deepseek")

MODELS_URL = "https://api.deepseek.com/models"


class DeepseekProvider(OpenAICompatProvider):
    echoes_prefill = False

    def __init__(self, api_key: str, model: str, params: dict):
        base_url = "https://api.deepseek.com/beta"
        super().__init__(base_url, api_key, model, params)

    async def fetch_models(self) -> list[dict]:
        headers = self._build_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(MODELS_URL, timeout=MODEL_FETCH_HTTP_TIMEOUT, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return data["data"]
        if isinstance(data, list):
            return data
        return []

    async def stream_complete(self, messages: list[dict], **kwargs):
        include_reasoning = kwargs.pop("include_reasoning", None)
        kwargs.pop("reasoning_effort", None)
        kwargs.pop("preserve_thinking", None)

        extra_body = kwargs.get("extra_body", {})
        if include_reasoning is False:
            extra_body["thinking"] = {"type": "disabled"}
        elif include_reasoning is True:
            extra_body["thinking"] = {"type": "enabled"}

        kwargs["extra_body"] = extra_body

        # Map msg["reasoning"] to the native reasoning_content field
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("reasoning"):
                msg["reasoning_content"] = msg.pop("reasoning")

        if messages and messages[-1].get("role") == "assistant":
            messages[-1]["prefix"] = True

        logger.debug("DeepSeek extra_body=%s", extra_body)
        async for chunk in super().stream_complete(messages, **kwargs):
            yield chunk
