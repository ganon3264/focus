from ..core.logger import get_logger
from .openai_compat import OpenAICompatProvider

logger = get_logger("providers.deepseek")


class DeepseekProvider(OpenAICompatProvider):
    echoes_prefill = False

    def __init__(self, api_key: str, model: str, params: dict):
        base_url = "https://api.deepseek.com/beta"
        super().__init__(base_url, api_key, model, params)

    async def stream_complete(self, messages: list[dict], **kwargs):
        include_reasoning = kwargs.pop("include_reasoning", None)
        kwargs.pop("reasoning_effort", None)

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
