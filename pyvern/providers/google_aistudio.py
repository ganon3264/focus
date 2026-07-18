import os
import base64
from google import genai
from google.genai import types

from .base import BaseProvider
from ..logger import get_logger

logger = get_logger("providers.google_aistudio")

class GoogleAIStudioProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, params: dict):
        super().__init__("", api_key, model, params)
        self.client = genai.Client(api_key=self.api_key or os.environ.get("GEMINI_API_KEY"))

    async def stream_complete(self, messages: list[dict], **kwargs):
        merged = {**self.params, **kwargs}

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
                            # data:image/png;base64,iVBOR...
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

        config_kwargs = {
            "temperature": merged.get("temperature", 1.0),
            "top_p": merged.get("top_p", 1.0),
            "top_k": merged.get("top_k", 0),
            "system_instruction": system_instruction,
            "safety_settings": [
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
            ]
        }
        
        max_tokens = merged.get("max_tokens")
        if max_tokens:
            config_kwargs["max_output_tokens"] = merged.get("max_output_tokens", max_tokens)
            
        stop = merged.get("stop")
        if stop:
            if isinstance(stop, str):
                stop = [stop]
            config_kwargs["stop_sequences"] = stop

        # Check if the user toggled thinking
        include_reasoning = merged.get("include_reasoning", False)
        reasoning_effort = merged.get("reasoning_effort", None)
        
        if include_reasoning or "gemini-3.1" in self.model or "gemini-2.0-flash-thinking" in self.model:
             config_kwargs.pop("temperature", None)
             thinking_kwargs = {"include_thoughts": True}
             if reasoning_effort:
                 thinking_kwargs["thinking_level"] = reasoning_effort
             config_kwargs["thinking_config"] = types.ThinkingConfig(**thinking_kwargs)

        config = types.GenerateContentConfig(**config_kwargs)

        logger.debug(f"AI Studio request: model={self.model}")

        async def _do_stream(contents):
            response_stream = await self.client.aio.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config
            )
            self._in_reasoning = False
            self._thought_signature_b64 = None
            
            async for chunk in response_stream:
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
