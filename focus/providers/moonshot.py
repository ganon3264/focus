from .openai_compat import OpenAICompatProvider


class MoonshotProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, model: str, params: dict):
        base_url = "https://api.moonshot.ai/v1"
        super().__init__(base_url, api_key, model, params)

    async def stream_complete(self, messages: list[dict], **kwargs):
        # Kimi-specific extension: the thinking parameter needs to be passed via the SDK's extra_body
        include_reasoning = kwargs.pop("include_reasoning", False)

        extra_body = kwargs.get("extra_body", {})
        if include_reasoning:
            extra_body["thinking"] = True

        kwargs["extra_body"] = extra_body

        async for chunk in super().stream_complete(messages, **kwargs):
            yield chunk
