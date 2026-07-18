from .openai_compat import OpenAICompatProvider

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, model: str, params: dict,
                 site_url: str = "", app_name: str = "Pyvern"):
        super().__init__(OPENROUTER_BASE, api_key, model, params)
        self.site_url = site_url
        self.app_name = app_name

    def _build_headers(self) -> dict:
        headers = super()._build_headers()
        headers["HTTP-Referer"] = self.site_url
        headers["X-Title"] = self.app_name
        return headers
