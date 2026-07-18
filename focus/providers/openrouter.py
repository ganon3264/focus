import httpx

from ..core.logger import get_logger
from .openai_compat import OpenAICompatProvider

logger = get_logger("providers.openrouter")

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, model: str, params: dict, site_url: str = "", app_name: str = "Focus"):
        super().__init__(OPENROUTER_BASE, api_key, model, params)
        self.site_url = site_url
        self.app_name = app_name

    async def fetch_models(self) -> list[dict]:
        from ..core.utils import MODEL_FETCH_HTTP_TIMEOUT

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/models",
                timeout=MODEL_FETCH_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return data["data"]
        if isinstance(data, list):
            return data
        return []

    def _extra_headers(self) -> dict:
        headers = super()._extra_headers()
        headers["HTTP-Referer"] = self.site_url
        headers["X-Title"] = self.app_name
        return headers

    def _get_provider_preferences(self) -> dict:
        prefs = {}
        # OpenRouter-specific routing params injected into extra_body
        or_route = self.params.get("or_route")
        or_quant = self.params.get("or_quant")
        or_no_fallbacks = self.params.get("or_no_fallbacks", True)

        provider_config = {}
        if or_route:
            provider_config["order"] = [or_route]
        if or_quant:
            provider_config["quantizations"] = [or_quant]
        if or_no_fallbacks:
            provider_config["allow_fallbacks"] = False

        if provider_config:
            prefs["provider"] = provider_config

        return prefs

    async def stream_complete(self, messages: list[dict], **kwargs):
        # Merge openrouter specific provider preferences into extra_body
        prefs = self._get_provider_preferences()
        extra_body = kwargs.get("extra_body", {})

        # Build reasoning object (OpenRouter unified API)
        include_reasoning = kwargs.pop("include_reasoning", False)
        reasoning_effort = kwargs.pop("reasoning_effort", "")
        thinking_budget = kwargs.pop("thinking_budget", 0)

        if include_reasoning:
            reasoning = {}
            if reasoning_effort and reasoning_effort.lower() != "default":
                reasoning["effort"] = reasoning_effort
            elif thinking_budget > 0:
                reasoning["max_tokens"] = thinking_budget
            else:
                reasoning["max_tokens"] = 2048
            extra_body["reasoning"] = reasoning

            if self.model.startswith("anthropic/claude"):
                kwargs.pop("temperature", None)
                kwargs.pop("top_p", None)
                kwargs.pop("top_k", None)
        else:
            extra_body["reasoning"] = {"enabled": False}

        if prefs:
            extra_body.update(prefs)

        kwargs["extra_body"] = extra_body

        logger.debug("OpenRouter routing extra_body=%s", kwargs.get("extra_body"))
        async for chunk in super().stream_complete(messages, **kwargs):
            yield chunk
