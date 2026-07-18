from .openai_compat import OpenAICompatProvider


class MoonshotProvider(OpenAICompatProvider):
    echoes_prefill = False

    def __init__(self, api_key: str, model: str, params: dict):
        base_url = "https://api.moonshot.ai/v1"
        super().__init__(base_url, api_key, model, params)

    async def stream_complete(self, messages: list[dict], **kwargs):
        include_reasoning = kwargs.pop("include_reasoning", None)
        preserve_thinking = kwargs.pop("preserve_thinking", False)

        extra_body = kwargs.get("extra_body", {})

        if include_reasoning is False:
            extra_body["thinking"] = {"type": "disabled"}
        elif include_reasoning is True:
            thinking = {"type": "enabled"}
            if preserve_thinking:
                thinking["keep"] = "all"
            extra_body["thinking"] = thinking

        kwargs["extra_body"] = extra_body

        if messages and messages[-1].get("role") == "assistant":
            messages[-1]["partial"] = True

        async for chunk in super().stream_complete(messages, **kwargs):
            yield chunk
