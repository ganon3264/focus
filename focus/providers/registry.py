"""Provider-type registry.

Adapters self-register via ``BaseProvider.__init_subclass__`` when their class
body declares a non-empty ``type``. This is the single type list: adding a
provider means adding one adapter module, nothing else.
"""

from __future__ import annotations

_REGISTRY: dict[str, type] = {}


def register(cls: type) -> None:
    _REGISTRY[cls.type] = cls


def get_provider_class(ptype: str) -> type:
    try:
        return _REGISTRY[ptype]
    except KeyError:
        raise ValueError(f"Unknown provider type: {ptype!r}") from None


def registered_types() -> list[str]:
    return sorted(_REGISTRY)


def profile_for(ptype: str):
    """Return the ProviderProfile for a provider type."""
    return get_provider_class(ptype).profile
