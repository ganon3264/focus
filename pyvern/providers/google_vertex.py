import base64
import json
import logging
from typing import AsyncIterator
import google.auth
from google.oauth2 import service_account
from google import genai
from google.genai import types

from .base import BaseProvider

logger = logging.getLogger(__name__)

class GoogleVertexProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, params: dict):
        super().__init__("", api_key, model, params)
        self.region = params.get("vertex_region", "")
        self.project_id = params.get("vertex_project_id", "")
        self.credentials = None
        
        # Try to parse the api_key as Service Account JSON
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
                # Let it be fatal if it looks like JSON but fails to load as credentials
                raise ValueError(f"Failed to parse api_key as Service Account JSON: {e}")
        
        # Fallback to Application Default Credentials if no JSON was provided
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
                timeout=300000, # 5 minutes timeout (in milliseconds)
                retryOptions=types.HttpRetryOptions(
                    attempts=3, # Retry up to 3 times for connection errors
                )
            )
        )

    async def stream_complete(
        self,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[str]:
        merged = {**self.params, **kwargs}
        
        # Prepare parameters for the model
        max_tokens = merged.pop("max_tokens", 1024)
        temperature = merged.pop("temperature", 1.0)
        top_p = merged.pop("top_p", None)
        top_k = merged.pop("top_k", None)
        stop = merged.pop("stop", None)

        system_instruction = None
        contents = []
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            # Helper to extract just text for system instructions
            def _extract_text(c):
                if isinstance(c, str):
                    return c
                if isinstance(c, list):
                    return "\n".join(part.get("text", "") for part in c if part.get("type") == "text")
                return str(c)

            # Helper to build GenAI Parts from OpenAI format
            def _build_parts(c):
                if isinstance(c, str):
                    return [types.Part.from_text(text=c)]
                parts = []
                if isinstance(c, list):
                    for part in c:
                        ptype = part.get("type")
                        if ptype == "text":
                            parts.append(types.Part.from_text(text=part.get("text", "")))
                        elif ptype == "image_url":
                            url = part.get("image_url", {}).get("url", "")
                            if url.startswith("data:"):
                                # data:image/png;base64,iVBOR...
                                mime_b64 = url[5:]
                                if ";base64," in mime_b64:
                                    mime, b64 = mime_b64.split(";base64,", 1)
                                    raw_bytes = base64.b64decode(b64)
                                    parts.append(types.Part.from_bytes(data=raw_bytes, mime_type=mime))
                return parts
            
            if role == "system":
                extracted = _extract_text(content)
                if system_instruction is None:
                    system_instruction = extracted
                else:
                    system_instruction += "\n\n" + extracted
            elif role == "user":
                contents.append(types.Content(role="user", parts=_build_parts(content)))
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=_build_parts(content)))

        config_args = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        
        # Check if the user is attempting to use reasoning models or enable thoughts natively
        if "gemini-3.1" in self.model or "gemini-2.0-flash-thinking" in self.model:
             config_args.pop("temperature", None)
             config_args["thinking_config"] = types.ThinkingConfig(include_thoughts=True)
             
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
            
        config = types.GenerateContentConfig(**config_args)
        
        stream = await self.client.aio.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=config,
        )
        
        self._in_reasoning = False
        
        async for chunk in stream:
            # Safely check for chunk.text directly first to ensure we always fall back gracefully
            if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                if chunk.text:
                    yield chunk.text
                continue
                
            # Iterate through parts for reasoning extraction
            for part in chunk.candidates[0].content.parts:
                is_thought = getattr(part, "thought", False) or (part.text and part.text.startswith("THOUGHT:"))
                
                if is_thought:
                    if not self._in_reasoning:
                        self._in_reasoning = True
                        yield "<think>\n"
                    
                    clean_text = part.text.replace("THOUGHT:", "") if part.text else ""
                    if getattr(part, "thought", False) and part.thought and not clean_text:
                        clean_text = part.thought
                        
                    if clean_text:
                        yield clean_text
                else:
                    if self._in_reasoning:
                        self._in_reasoning = False
                        yield "\n</think>\n\n"
                    
                    if part.text:
                        yield part.text
