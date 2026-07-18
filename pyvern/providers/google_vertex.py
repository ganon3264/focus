import base64
import json
from typing import AsyncIterator
import google.auth
from google.oauth2 import service_account
from google import genai
from google.genai import types

from .base import BaseProvider
from ..logger import get_logger

logger = get_logger("providers.google_vertex")

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
                async_client_args={
                    "timeout": 300.0, # 5 minutes timeout (in seconds for Python)
                    "retries": 3      # Standard httpx retry count
                }
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

        # Helper to extract just text for system instructions
        def _extract_text(c):
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return "\n".join(part.get("text", "") for part in c if part.get("type") == "text")
            return str(c)

        # Helper to build GenAI Parts from OpenAI format
        def _build_parts(c, reasoning=None, thought_signature_b64=None):
            parts = []
            if reasoning:
                parts.append(types.Part(text=reasoning, thought=True))
            
            sig_bytes = base64.b64decode(thought_signature_b64) if thought_signature_b64 else None
            
            if isinstance(c, str):
                parts.append(types.Part(text=c, thought_signature=sig_bytes))
                return parts
            
            if isinstance(c, list):
                sig_attached = False
                for part in c:
                    ptype = part.get("type")
                    if ptype == "text":
                        kwargs = {"text": part.get("text", "")}
                        if sig_bytes and not sig_attached:
                            kwargs["thought_signature"] = sig_bytes
                            sig_attached = True
                        parts.append(types.Part(**kwargs))
                    elif ptype == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if url.startswith("data:"):
                            mime_b64 = url[5:]
                            if ";base64," in mime_b64:
                                mime, b64 = mime_b64.split(";base64,", 1)
                                raw_bytes = base64.b64decode(b64)
                                parts.append(types.Part.from_bytes(data=raw_bytes, mime_type=mime))
                if sig_bytes and not sig_attached:
                    parts.append(types.Part(thought_signature=sig_bytes))
            return parts

        # Only the last assistant turn may carry a thought_signature
        last_assistant_idx = None
        for i, m in enumerate(messages):
            if m.get("role") == "assistant" and m.get("thought_signature"):
                last_assistant_idx = i

        def _build_contents(include_sig):
            system_instruction = None
            contents = []
            for msg_idx, msg in enumerate(messages):
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "system":
                    extracted = _extract_text(content)
                    if system_instruction is None:
                        system_instruction = extracted
                    else:
                        system_instruction += "\n\n" + extracted
                elif role == "user":
                    contents.append(types.Content(role="user", parts=_build_parts(content)))
                elif role == "assistant":
                    reasoning = msg.get("reasoning") if merged.get("send_reasoning_history", True) else None
                    thought_sig = msg.get("thought_signature") if (include_sig and msg_idx == last_assistant_idx and merged.get("send_reasoning_history", True)) else None
                    contents.append(types.Content(role="model", parts=_build_parts(content, reasoning, thought_sig)))
            return system_instruction, contents

        system_instruction, contents = _build_contents(include_sig=True)

        config_args = {
            "temperature": temperature,
            "max_output_tokens": merged.get("max_output_tokens", max_tokens),
            "safety_settings": [
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_IMAGE_HATE", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_IMAGE_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_IMAGE_HARASSMENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_IMAGE_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_JAILBREAK", threshold="OFF")
            ]
        }
        
        # Check if the user is attempting to use reasoning models or enable thoughts natively
        include_reasoning = merged.pop("include_reasoning", False)
        reasoning_effort = merged.pop("reasoning_effort", None)
        
        if include_reasoning or "gemini-3.1" in self.model or "gemini-2.0-flash-thinking" in self.model:
             config_args.pop("temperature", None)
             thinking_kwargs = {"include_thoughts": True}
             if reasoning_effort:
                 thinking_kwargs["thinking_level"] = reasoning_effort
             config_args["thinking_config"] = types.ThinkingConfig(**thinking_kwargs)
             
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
        
        logger.debug(f"Vertex request: model={self.model}, project={self.project_id}, region={self.region}, max_tokens={max_tokens}")
        
        async def _do_stream(contents):
            stream = await self.client.aio.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            )
            self._in_reasoning = False
            self._thought_signature_b64 = None
            
            async for chunk in stream:
                if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                    if chunk.text:
                        yield chunk.text
                    continue
                    
                for part in chunk.candidates[0].content.parts:
                    if hasattr(part, "thought_signature") and part.thought_signature:
                        self._thought_signature_b64 = base64.b64encode(part.thought_signature).decode("utf-8")

                    is_thought = getattr(part, "thought", False) or (part.text and part.text.startswith("THOUGHT:"))
                    
                    if is_thought:
                        if not self._in_reasoning:
                            self._in_reasoning = True
                            yield "<think>\n"
                        
                        clean_text = part.text.replace("THOUGHT:", "") if part.text else ""
                            
                        if clean_text:
                            yield clean_text
                    else:
                        if self._in_reasoning:
                            self._in_reasoning = False
                            yield "\n</think>\n\n"
                        
                        if part.text:
                            yield part.text
                            
            if self._in_reasoning:
                self._in_reasoning = False
                yield "\n</think>\n\n"
                
            if self._thought_signature_b64:
                yield f"\n<thought_signature>{self._thought_signature_b64}</thought_signature>"

        try:
            async for chunk in _do_stream(contents):
                yield chunk
        except Exception:
            if last_assistant_idx is not None and _build_contents:
                _, contents_retry = _build_contents(include_sig=False)
                async for chunk in _do_stream(contents_retry):
                    yield chunk
            else:
                raise
