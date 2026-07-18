from .openai_compat import OpenAICompatProvider

class GoogleAIStudioProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, model: str, params: dict):
        # AI Studio uses OpenAI compat endpoint
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        super().__init__(base_url, api_key, model, params)
