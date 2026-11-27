from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx

from ..core.utils import MODEL_FETCH_HTTP_TIMEOUT, OPENAI_HTTP_TIMEOUT
from .config import ProviderConfig
from .profile import Capabilities, ProviderProfile
from .registry import register

# One transport for every outbound provider call. An SDK client is a thin
# wrapper carrying base_url, key and headers — all of which are rebuilt per
# call anyway — so sharing the transport costs nothing and stops each send and
# each tool round from paying its own DNS + TLS handshake. Never closed per
# request; the app closes it on shutdown.
HTTP_CLIENT = httpx.AsyncClient(timeout=OPENAI_HTTP_TIMEOUT, follow_redirects=True)


def shared_client() -> httpx.AsyncClient:
    """Resolved per call so the module attribute stays the one seam."""
    return HTTP_CLIENT


async def close_shared_client() -> None:
    await HTTP_CLIENT.aclose()


def sdk_dump(obj) -> object:
    """Best-effort plain-data view of an upstream SDK object for debug logs."""
    dump = getattr(obj, "model_dump", None)
    if dump is not None:
        try:
            return dump(mode="json", exclude_none=True)
        except Exception:
            pass
    if isinstance(obj, dict):
        return {k: sdk_dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sdk_dump(v) for v in obj]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    try:
        return {k: sdk_dump(v) for k, v in vars(obj).items() if not k.startswith("_")}
    except TypeError:
        return repr(obj)


def _apply_caps(cls: type) -> None:
    """Copy a profile's capability flags onto the class.

    Keeps ``Provider.supports_tools`` / ``supports_prefill`` / ``echoes_prefill``
    working at both class and instance level while the profile stays the single
    source of truth.
    """
    prof = getattr(cls, "profile", None)
    if prof is None:
        return
    cls.supports_tools = prof.caps.supports_tools
    cls.supports_prefill = prof.caps.supports_prefill
    cls.echoes_prefill = prof.caps.echoes_prefill
    cls._include_stream_options = prof.caps.include_stream_options


class BaseProvider(ABC):
    type: str = ""
    profile: ProviderProfile = ProviderProfile(caps=Capabilities())

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _apply_caps(cls)
        if cls.__dict__.get("type"):
            register(cls)

    @classmethod
    def from_row(cls, row: dict, params: dict, config: ProviderConfig) -> "BaseProvider":
        """Construct an instance from a provider DB row. Overridden per type."""
        raise NotImplementedError(f"{cls.__name__} must implement from_row()")

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        params: dict,
        config: ProviderConfig | None = None,
    ):
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.api_key = api_key or ""
        self.model = model
        self.params = params  # upstream sampler defaults (top_p, rep_pen, ...)
        self.config = config or ProviderConfig()  # Focus-only settings, never sent upstream

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        key = self.api_key.strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    async def fetch_models(self) -> list[dict]:
        """Fetch available models from this provider.

        Returns a list of dicts with at least an ``id`` key.
        The default implementation hits ``GET {base_url}/models`` with
        ``_build_headers()``.  Override for providers with a different API.
        """
        url = f"{self.base_url}/models"
        headers = self._build_headers()
        extra = getattr(self, "_extra_headers", None)
        if extra:
            headers.update(extra())
        resp = await shared_client().get(url, timeout=MODEL_FETCH_HTTP_TIMEOUT, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return data["data"]
        if isinstance(data, list):
            return data
        return []

    async def supported_modalities(self, model: str) -> list[str] | None:
        """Input modalities *model* accepts, or ``None`` when unknown.

        The request pipeline strips media the model can't consume. Returning
        ``None`` (the default) means "don't filter"; routers that expose a
        per-model modality list override this.
        """
        return None

    async def supported_parameters(self, model: str) -> list[str] | None:
        """Sampler parameter names *model* accepts, or ``None`` when unknown.

        The request pipeline drops forwarded sampler keys the model doesn't
        advertise. Returning ``None`` (the default) means "don't filter";
        routers that expose a per-model parameter list override this.
        """
        return None

    @abstractmethod
    async def stream_complete(
        self,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[dict]:
        """Produce a completion, yielding dict events.

        Event types:
          {"type": "token", "text": str}
          {"type": "tool_calls", "calls": list[ToolCall]}
          {"type": "usage", "usage": dict}
          {"type": "done"}

        ``stream`` (default True) selects the upstream API mode: a normal
        streaming request, or one non-streaming call whose complete response is
        replayed through the same events. The event contract is identical
        either way; callers never need to know which was used.
        """


_apply_caps(BaseProvider)
