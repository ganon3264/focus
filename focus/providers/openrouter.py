from dataclasses import replace

import httpx

from ..core.logger import get_logger
from ..core.utils import MODEL_FETCH_HTTP_TIMEOUT, TTLCache
from .config import ProviderConfig
from .openai_compat import OpenAICompatProvider
from .profile import ProviderProfile

logger = get_logger("providers.openrouter")

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Shared across instances: the public model list is the same for every key.
_models_cache = TTLCache()


class OpenRouterProvider(OpenAICompatProvider):
    type = "openrouter"
    profile = ProviderProfile(
        caps=replace(
            OpenAICompatProvider.profile.caps,
            include_stream_options=False,
            supports_ephemeral_cache=True,
            reasoning_formats=None,
            normalizes_reasoning=True,
        ),
        context_kwargs=("session_id",),
    )

    def __init__(
        self,
        api_key: str,
        model: str,
        params: dict,
        config: ProviderConfig | None = None,
        site_url: str = "",
        app_name: str = "Focus",
    ):
        super().__init__(OPENROUTER_BASE, api_key, model, params, config=config)
        self.site_url = site_url
        self.app_name = app_name

    @classmethod
    def from_row(cls, row: dict, params: dict, config: ProviderConfig) -> "OpenRouterProvider":
        return cls(api_key=row["api_key"] or "", model=row["model"], params=params, config=config)

    async def fetch_models(self) -> list[dict]:
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

    async def _model_entry(self, model: str) -> dict | None:
        async def _fetch():
            return await self.fetch_models()

        models = await _models_cache.get_or_refresh("models", _fetch)
        if not models:
            return None
        for m in models:
            if isinstance(m, dict) and m.get("id") == model:
                return m
        return None

    async def supported_modalities(self, model: str) -> list[str] | None:
        entry = await self._model_entry(model)
        arch = entry.get("architecture") if entry else None
        return arch.get("input_modalities") if isinstance(arch, dict) else None

    async def supported_parameters(self, model: str) -> list[str] | None:
        entry = await self._model_entry(model)
        params = entry.get("supported_parameters") if entry else None
        return params if isinstance(params, list) else None

    def _extra_headers(self) -> dict:
        headers = super()._extra_headers()
        headers["HTTP-Referer"] = self.site_url
        headers["X-Title"] = self.app_name
        return headers

    def _get_provider_preferences(self) -> dict:
        prefs = {}
        or_route = self.config.or_route
        or_quant = self.config.or_quant
        or_no_fallbacks = self.config.or_no_fallbacks

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
        prefs = self._get_provider_preferences()
        extra_body = kwargs.get("extra_body", {})

        include_reasoning = kwargs.pop("include_reasoning", False)
        reasoning_effort = kwargs.pop("reasoning_effort", "")
        thinking_budget = kwargs.pop("thinking_budget", 0)
        reasoning_context = kwargs.pop("reasoning_context", None)
        reasoning_mode = kwargs.pop("reasoning_mode", None)
        kwargs.pop("preserve_thinking", None)

        if include_reasoning:
            reasoning = {}
            if reasoning_effort and reasoning_effort.lower() != "default":
                reasoning["effort"] = reasoning_effort
            elif thinking_budget > 0:
                reasoning["max_tokens"] = thinking_budget
            else:
                reasoning["max_tokens"] = 2048
            if reasoning_context:
                reasoning["context"] = reasoning_context
            if reasoning_mode:
                reasoning["mode"] = reasoning_mode
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
