import json
import google.auth
from google.oauth2 import service_account
from google import genai
from google.genai import types

from .google_base import GoogleProviderBase, VERTEX_SAFETY_OFF
from ..logger import get_logger
from ..utils import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE, GOOGLE_VERTEX_HTTP_TIMEOUT, GOOGLE_VERTEX_HTTP_RETRIES

logger = get_logger("providers.google_vertex")


class GoogleVertexProvider(GoogleProviderBase):
    def __init__(self, api_key: str, model: str, params: dict):
        super().__init__(api_key, model, params)
        self.region = params.get("vertex_region", "")
        self.project_id = params.get("vertex_project_id", "")
        self.credentials = None

        if api_key and api_key.strip().startswith("{"):
            try:
                sa_info = json.loads(api_key)
                self.credentials = service_account.Credentials.from_service_account_info(
                    sa_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                if not self.project_id:
                    self.project_id = sa_info.get("project_id", "")
            except Exception as e:
                raise ValueError(f"Failed to parse api_key as Service Account JSON: {e}")

        if not self.credentials:
            try:
                self.credentials, adc_project_id = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                if not self.project_id:
                    self.project_id = adc_project_id
            except Exception as e:
                raise ValueError(f"Failed to load ADC credentials. Are you logged in via gcloud? Error: {e}")

        if not self.project_id or not self.region:
            raise ValueError("Vertex AI requires a Project ID and Region")

        self.client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.region,
            credentials=self.credentials,
            http_options=types.HttpOptions(
                async_client_args={
                    "timeout": GOOGLE_VERTEX_HTTP_TIMEOUT,
                    "retries": GOOGLE_VERTEX_HTTP_RETRIES,
                }
            )
        )

    async def fetch_models(self) -> list[dict]:
        vertex_models = await self.client.aio.models.list()
        models = []
        async for m in vertex_models:
            model_id = m.name.split("/")[-1] if "/" in m.name else m.name
            models.append({"id": model_id, "name": model_id})
        return models

    def _build_config(self, merged: dict, system_instruction: str | None) -> types.GenerateContentConfig:
        max_tokens = merged.pop("max_tokens", DEFAULT_MAX_TOKENS)
        temperature = merged.pop("temperature", DEFAULT_TEMPERATURE)
        top_p = merged.pop("top_p", None)
        top_k = merged.pop("top_k", None)
        stop = merged.pop("stop", None)
        include_reasoning = merged.pop("include_reasoning", False)
        reasoning_effort = merged.pop("reasoning_effort", None)

        config_args: dict = {
            "temperature": temperature,
            "max_output_tokens": merged.get("max_output_tokens", max_tokens),
            "safety_settings": VERTEX_SAFETY_OFF,
        }

        self._apply_thinking_config(config_args, self.model, include_reasoning, reasoning_effort)

        if top_p is not None:
            config_args["top_p"] = top_p
        if top_k is not None:
            config_args["top_k"] = top_k
        if stop is not None:
            if isinstance(stop, str):
                stop = [stop]
            config_args["stop_sequences"] = stop
        if system_instruction is not None:
            config_args["system_instruction"] = system_instruction

        logger.debug(f"Vertex request: model={self.model}, project={self.project_id}, region={self.region}, max_tokens={max_tokens}")
        return types.GenerateContentConfig(**config_args)
