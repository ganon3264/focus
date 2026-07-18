import os
from google import genai
from google.genai import types

from .google_base import GoogleProviderBase, AI_STUDIO_SAFETY_OFF
from ..logger import get_logger
from ..utils import DEFAULT_TEMPERATURE

logger = get_logger("providers.google_aistudio")


class GoogleAIStudioProvider(GoogleProviderBase):
    def __init__(self, api_key: str, model: str, params: dict):
        super().__init__(api_key, model, params)
        self.client = genai.Client(api_key=self.api_key or os.environ.get("GEMINI_API_KEY"))

    async def fetch_models(self) -> list[dict]:
        aistudio_models = await self.client.aio.models.list()
        models = []
        async for m in aistudio_models:
            model_id = m.name.split("/")[-1] if "/" in m.name else m.name
            models.append({"id": model_id, "name": model_id})
        return models

    def _build_config(self, merged: dict, system_instruction: str | None) -> types.GenerateContentConfig:
        include_reasoning = merged.get("include_reasoning", False)
        reasoning_effort = merged.get("reasoning_effort", None)

        config_kwargs = {
            "temperature": merged.get("temperature", DEFAULT_TEMPERATURE),
            "top_p": merged.get("top_p", DEFAULT_TEMPERATURE),
            "top_k": merged.get("top_k", 0),
            "system_instruction": system_instruction,
            "safety_settings": AI_STUDIO_SAFETY_OFF,
        }

        max_tokens = merged.get("max_tokens")
        if max_tokens:
            config_kwargs["max_output_tokens"] = merged.get("max_output_tokens", max_tokens)

        stop = merged.get("stop")
        if stop:
            if isinstance(stop, str):
                stop = [stop]
            config_kwargs["stop_sequences"] = stop

        self._apply_thinking_config(config_kwargs, self.model, include_reasoning, reasoning_effort)

        logger.debug(f"AI Studio request: model={self.model}")
        return types.GenerateContentConfig(**config_kwargs)
