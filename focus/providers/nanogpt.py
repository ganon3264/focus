"""NanoGPT aggregator (OpenAI Chat Completions compatible).

NanoGPT fronts a large set of upstream hosts behind one OpenAI-shaped API, so
most of the wire format is the inherited one. Three things need mapping:

* upstream pinning goes in the request body (``provider.only``), merged into
  ``extra_body`` next to the samplers; NanoGPT's pin is hard by nature;
* prompt caching rides the standard Anthropic ``cache_control`` breakpoints,
  applied by the ``claude_cache`` quirk like every other transport;
* the model catalogue is rich (context window, modalities, pricing, upstream
  list) and is fetched with ``detailed=true``.
"""

from dataclasses import replace
from urllib.parse import quote

import httpx

from ..core.logger import get_logger
from ..core.utils import MODEL_FETCH_HTTP_TIMEOUT, TTLCache
from .config import ProviderConfig
from .openai_compat import OpenAICompatProvider
from .profile import ProviderProfile

logger = get_logger("providers.nanogpt")

NANOGPT_BASE = "https://api.nano-gpt.com/api/v1"
# Provider discovery sits on the origin, *not* under the /api/v1 base URL, and
# takes the model id URL-encoded so its slash isn't a path separator.
NANOGPT_API_ORIGIN = "https://api.nano-gpt.com"

# Both catalogues are public and identical for every key, so one cache serves all.
_models_cache = TTLCache()
_providers_cache = TTLCache()


class NanoGPTProvider(OpenAICompatProvider):
    type = "nanogpt"
    profile = ProviderProfile(
        caps=replace(
            OpenAICompatProvider.profile.caps,
            supports_ephemeral_cache=True,
            cache_breakpoints=True,
            normalizes_reasoning=True,
        ),
    )

    def __init__(
        self,
        api_key: str,
        model: str,
        params: dict,
        config: ProviderConfig | None = None,
        base_url: str = NANOGPT_BASE,
    ):
        super().__init__(base_url or NANOGPT_BASE, api_key, model, params, config=config)

    @classmethod
    def from_row(cls, row: dict, params: dict, config: ProviderConfig) -> "NanoGPTProvider":
        return cls(
            base_url=row["base_url"] or NANOGPT_BASE,
            api_key=row["api_key"] or "",
            model=row["model"],
            params=params,
            config=config,
        )

    async def fetch_models(self) -> list[dict]:
        headers = self._build_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/models",
                params={"detailed": "true"},
                timeout=MODEL_FETCH_HTTP_TIMEOUT,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data, list):
            return data
        return []

    async def model_entry(self, model: str) -> dict | None:
        """Catalogue entry for *model*, cached for the whole model list TTL."""
        async def _fetch():
            return await self.fetch_models()

        models = await _models_cache.get_or_refresh("models", _fetch)
        for m in models or []:
            if isinstance(m, dict) and m.get("id") == model:
                return m
        return None

    async def supported_modalities(self, model: str) -> list[str] | None:
        entry = await self.model_entry(model)
        arch = entry.get("architecture") if entry else None
        modalities = arch.get("input_modalities") if isinstance(arch, dict) else None
        return modalities if isinstance(modalities, list) else None

    async def provider_discovery(self, model: str) -> dict:
        """Routing metadata for *model*, cached per model id.

        The catalogue's ``providers`` array is not the provider-selection list
        (NanoGPT says so explicitly); this endpoint is, and it is the only one
        that reports ``supportsProviderSelection``. It is public, so an empty
        key is enough — the catalogue is identical for every caller.
        """
        async def _fetch():
            url = f"{NANOGPT_API_ORIGIN}/api/models/{quote(model, safe='')}/providers"
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url, timeout=MODEL_FETCH_HTTP_TIMEOUT, headers=self._build_headers()
                )
                resp.raise_for_status()
                return resp.json()

        return await _providers_cache.get_or_refresh(model, _fetch)

    async def model_routes(self, model: str) -> dict:
        """Pinnable hosts for *model*, plus whether a pin means anything here.

        ``providers`` carries the selectable list on models that support
        provider selection; single-route models answer with ``providerDetails``
        instead, where a pin is still a hard constraint the route must satisfy.
        A model that routes automatically answers with neither and says why, so
        the picker can explain itself instead of rendering an empty list.
        """
        data = await self.provider_discovery(model)
        rows = data.get("providers") or data.get("providerDetails") or []
        options = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("provider"):
                continue
            if row.get("available") is False:
                continue
            provider_id = row["provider"]
            options.append({
                "id": provider_id,
                "label": row.get("displayName") or provider_id,
            })
        options.sort(key=lambda o: o["label"].lower())
        return {
            "options": options,
            "supports_selection": bool(data.get("supportsProviderSelection")),
            "message": None if options else (
                data.get("message") or "No pinnable providers for this model."
            ),
        }

    def _routing(self) -> dict:
        """Hard-pin the chosen host.

        ``only`` is already a hard constraint on NanoGPT ("fails instead of
        routing outside the list"), unlike OpenRouter's soft ``order``, so a
        toggle would have nothing to switch.
        """
        route = self.config.ng_route
        if not route:
            return {}
        return {"provider": {"only": [route]}}

    async def stream_complete(self, messages: list[dict], **kwargs):
        include_reasoning = kwargs.pop("include_reasoning", True)
        kwargs.pop("preserve_thinking", None)

        extra_body = kwargs.get("extra_body", {})
        if not include_reasoning:
            extra_body["reasoning"] = {"exclude": True}
        extra_body.update(self._routing())
        kwargs["extra_body"] = extra_body

        logger.debug("NanoGPT extra_body=%s", extra_body)
        async for chunk in super().stream_complete(messages, **kwargs):
            yield chunk
