from dataclasses import replace

from .config import ProviderConfig
from .openai_compat import OpenAICompatProvider
from .profile import ProviderProfile


class MoonshotProvider(OpenAICompatProvider):
    type = "moonshot"
    profile = ProviderProfile(
        caps=replace(
            OpenAICompatProvider.profile.caps,
            echoes_prefill=False,
            reasoning_message_key="reasoning_content",
            reasoning_formats=(),
        ),
        context_kwargs=("prompt_cache_key",),
    )

    def __init__(self, api_key: str, model: str, params: dict, config: ProviderConfig | None = None):
        base_url = "https://api.moonshot.ai/v1"
        super().__init__(base_url, api_key, model, params, config=config)

    @classmethod
    def from_row(cls, row: dict, params: dict, config: ProviderConfig) -> "MoonshotProvider":
        return cls(api_key=row["api_key"] or "", model=row["model"], params=params, config=config)

    async def stream_complete(self, messages: list[dict], **kwargs):
        include_reasoning = kwargs.pop("include_reasoning", None)
        preserve_thinking = kwargs.pop("preserve_thinking", "tool_only")
        reasoning_effort = kwargs.pop("reasoning_effort", "")

        extra_body = kwargs.get("extra_body", {})

        if include_reasoning is False:
            extra_body["thinking"] = {"type": "disabled"}
        elif include_reasoning is True:
            thinking = {"type": "enabled"}
            if preserve_thinking == "all" or preserve_thinking is True:
                thinking["keep"] = "all"
            extra_body["thinking"] = thinking
            if reasoning_effort:
                extra_body["reasoning_effort"] = reasoning_effort

        kwargs["extra_body"] = extra_body

        if messages and messages[-1].get("role") == "assistant":
            messages[-1]["partial"] = True

        async for chunk in super().stream_complete(messages, **kwargs):
            yield chunk
