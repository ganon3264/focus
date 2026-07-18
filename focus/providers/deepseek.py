from .openai_compat import OpenAICompatProvider

class DeepseekProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, model: str, params: dict):
        base_url = "https://api.deepseek.com/v1"
        super().__init__(base_url, api_key, model, params)
