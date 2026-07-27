from __future__ import annotations

from typing import Any

TRACKED_FIELDS: dict[str, dict] = {
    "reasoning": {
        "delta_keys": ("reasoning_content", "reasoning"),
        "merge": "append",
        "preserve_thinking": True,
        "history_key": "reasoning",
        "stream_to_sse": True,
    },
    "reasoning_details": {
        "delta_keys": ("reasoning_details",),
        "merge": "index",
        "preserve_thinking": True,
        "history_key": "reasoning_details",
        "stream_to_sse": False,
    },
}

_PT_FIELDS = [cfg for cfg in TRACKED_FIELDS.values() if cfg.get("preserve_thinking")]


def merge_delta(store: list | dict, name: str, value: Any) -> None:
    """Merge a single delta *value* for tracked field *name* into *store*.

    *store* is mutated in-place.  For ``"append"`` fields *store* is a
    ``list``; for ``"index"`` fields it is a ``dict`` keyed by id/index.
    """
    cfg = TRACKED_FIELDS.get(name)
    if cfg is None:
        return
    if cfg["merge"] == "append":
        store.append(value)  # type: ignore[union-attr]
    elif cfg["merge"] == "index":
        items = value if isinstance(value, list) else [value]
        d = store  # type: ignore[assignment]
        for item in items:
            key = item.get("id") if item.get("id") is not None else item.get("index")
            if key is not None:
                existing = d.get(key)
                if existing:
                    if item.get("text"):
                        existing["text"] = (existing.get("text") or "") + item["text"]
                    if item.get("signature"):
                        existing["signature"] = item["signature"]
                else:
                    d[key] = dict(item)


def get_field(accumulated: list | dict | str | None, name: str):
    """Return the final value for tracked field *name* from its accumulated state.

    Accepts a list (streaming accumulation), a plain string (preset block),
    or a dict (index-merged accumulation).  Returns ``None`` when empty.
    """
    cfg = TRACKED_FIELDS.get(name)
    if cfg is None or not accumulated:
        return None
    if cfg["merge"] == "append":
        if isinstance(accumulated, str):
            r = accumulated.strip()
        else:
            r = "".join(accumulated).strip()  # type: ignore[union-attr]
        return r or None
    elif cfg["merge"] == "index":
        if isinstance(accumulated, dict):
            r = sorted(
                accumulated.values(),
                key=lambda x: (
                    x.get("index") if x.get("index") is not None else float("inf"),
                    x.get("id") or "",
                ),
            )
            return r or None
        return accumulated if accumulated else None
    return None


def build_full_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Build the final variant_meta dict from raw accumulated *meta*."""
    result: dict[str, Any] = {}
    for name in TRACKED_FIELDS:
        val = get_field(meta.get(name), name)
        if val is not None:
            result[name] = val
    return result


def attach_to_message(msg: dict, meta: dict[str, Any]) -> None:
    """Attach tracked fields from *meta* onto *msg* at their ``history_key``."""
    for name, cfg in TRACKED_FIELDS.items():
        raw = meta.get(name)
        if raw:
            val = get_field(raw, name)
            if val is not None:
                msg[cfg["history_key"]] = val


_COMPATIBLE_FORMATS: dict[str, tuple[str, ...] | None] = {
    "openai_compat": ("openai",),
    "openrouter": None,  # pass everything — router handles multiple backends
    "deepseek": ("deepseek",),
    "moonshot": (),
    "google_aistudio": ("google",),
    "google_vertex": ("google",),
}


def filter_reasoning_details(msg: dict, prov_type: str) -> None:
    """Remove ``reasoning_details`` items whose format is incompatible with *prov_type*.

    Each reasoning_details item carries a ``"format"`` field like
    ``"anthropic-claude-v1"`` or ``"openai-responses-v1"``.  Items whose
    format prefix doesn't match the current provider are stripped to avoid
    sending provider-specific schemas (signatures, encrypted blobs) to a
    different provider.
    """
    rd = msg.get("reasoning_details")
    if not rd or not isinstance(rd, list):
        return
    ok = _COMPATIBLE_FORMATS.get(prov_type)
    if ok is None:
        return  # openrouter — keep everything
    filtered = [i for i in rd if not i.get("format") or any(i["format"].startswith(p) for p in ok)]
    if len(filtered) != len(rd):
        msg["reasoning_details"] = filtered if filtered else None


def strip_thinking(msg: dict, mode: str) -> None:
    """Remove ``preserve_thinking`` fields from *msg*."""
    if mode == "off":
        for cfg in _PT_FIELDS:
            msg.pop(cfg["history_key"], None)
    elif mode == "tool_only":
        has_pt = any(msg.get(cfg["history_key"]) for cfg in _PT_FIELDS)
        if has_pt and not msg.get("tool_calls") and msg.get("content"):
            for cfg in _PT_FIELDS:
                msg.pop(cfg["history_key"], None)
