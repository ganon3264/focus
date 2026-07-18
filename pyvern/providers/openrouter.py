from .openai_compat import OpenAICompatProvider

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, model: str, params: dict,
                 site_url: str = "", app_name: str = "Pyvern"):
        super().__init__(OPENROUTER_BASE, api_key, model, params)
        self.site_url = site_url
        self.app_name = app_name

    def _extra_headers(self) -> dict:
        headers = super()._extra_headers()
        headers["HTTP-Referer"] = self.site_url
        headers["X-Title"] = self.app_name
        return headers

    def _get_provider_preferences(self) -> dict:
        prefs = {}
        # OpenRouter-specific routing params injected into extra_body
        or_route = self.params.pop("or_route", None)
        or_quant = self.params.pop("or_quant", None)
        
        provider_config = {}
        if or_route:
            provider_config["order"] = [or_route]
            provider_config["allow_fallbacks"] = False
        if or_quant:
            provider_config["quantizations"] = [or_quant]
            
        if provider_config:
            prefs["provider"] = provider_config
            
        return prefs

    async def stream_complete(self, messages: list[dict], **kwargs):
        # Merge openrouter specific provider preferences into extra_body
        prefs = self._get_provider_preferences()
        if prefs:
            extra_body = kwargs.get("extra_body", {})
            extra_body.update(prefs)
            kwargs["extra_body"] = extra_body
            
        async for chunk in super().stream_complete(messages, **kwargs):
            yield chunk

