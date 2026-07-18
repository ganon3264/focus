import re

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

        # Transform messages for Moonshot API format:
        #   - Extract <think> blocks from content into reasoning_content field
        #   - Strip <think> blocks from content
        #   - Map msg["reasoning"] (from assemble_prompt) to reasoning_content
        for msg in messages:
            if msg.get("role") == "assistant" and isinstance(msg.get("content"), str):
                content = msg["content"]
                reasoning_parts = []

                text = re.sub(
                    r"<think>([\s\S]*?)</think>",
                    lambda m: reasoning_parts.append(m.group(1)) or "",
                    content,
                )
                text = re.sub(
                    r"<think>([\s\S]*)$",
                    lambda m: reasoning_parts.append(m.group(1)) or "",
                    text,
                )
                text = text.strip()

                if not reasoning_parts and msg.get("reasoning"):
                    reasoning_parts = [msg["reasoning"]]

                if reasoning_parts:
                    msg["reasoning_content"] = "\n\n".join(
                        r.strip() for r in reasoning_parts if r.strip()
                    )
                    msg["content"] = text if text else ""

        if messages and messages[-1].get("role") == "assistant":
            messages[-1]["partial"] = True

        async for chunk in super().stream_complete(messages, **kwargs):
            yield chunk
