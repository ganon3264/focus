"""Readout for one message's provider usage.

A message is one bubble in the chat, but with tools enabled the provider was
called once per round and ``generation_usage`` stores a row per call. The
bubble's figures are sums over those rows; the per-call rows stay available for
the breakdown. Cost fields are whatever the upstream chose to report — most
providers report none, so absence is rendered as an em dash, never as zero.
"""

from __future__ import annotations

import json

_TOKEN_ROWS = (
    ("prompt_tokens", "Prompt"),
    ("cached_tokens", "Cached"),
    ("completion_tokens", "Completion"),
    ("reasoning_tokens", "Reasoning"),
    ("total_tokens", "Total"),
)


def _money(value) -> str | None:
    """Cents only. Anything below a cent is stated, not rounded to zero."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if amount == 0:
        return "$0"
    if amount < 0.005:
        return "<$0.01"
    return f"${amount:.2f}"


def _parse_details(raw) -> dict:
    try:
        details = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    return details if isinstance(details, dict) else {}


def _detail_value(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return _money(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _detail_rows(details: dict) -> list[dict]:
    return [
        {"label": key.replace("_", " ").capitalize(), "value": _detail_value(value)}
        for key, value in details.items()
    ]


def _stat_rows(totals: dict) -> list[dict]:
    prompt = totals["prompt_tokens"]
    cached = totals["cached_tokens"]
    # A provider that reports no total still reports its halves; the total row
    # must not read zero above two non-zero ones.
    total = totals["total_tokens"] or prompt + totals["completion_tokens"]
    rows = []
    for key, label in _TOKEN_ROWS:
        if key in ("cached_tokens", "reasoning_tokens") and not totals[key]:
            continue
        value = f"{(total if key == 'total_tokens' else totals[key]):,}"
        if key == "cached_tokens" and prompt:
            value += f" ({cached / prompt * 100:.0f}%)"
        rows.append({"label": label, "value": value})
    return rows


def summarize_usage(rows: list[dict]) -> dict:
    totals = {key: 0 for key, _ in _TOKEN_ROWS}
    calls: list[dict] = []
    details: dict = {}
    cost = None
    model = ""
    provider_type = ""

    for index, row in enumerate(rows):
        for key in totals:
            totals[key] += int(row.get(key) or 0)

        for key, value in _parse_details(row.get("cost_details")).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                details[key] = details.get(key, 0) + value
            else:
                details.setdefault(key, value)

        if row.get("cost") is not None:
            cost = (cost or 0.0) + float(row["cost"])

        model = row.get("model_name") or model
        provider_type = row.get("provider_type") or provider_type
        calls.append({
            "label": f"Call {index + 1}",
            "model": row.get("model_name") or "",
            "tokens": f"{int(row.get('prompt_tokens') or 0):,} → {int(row.get('completion_tokens') or 0):,}",
            "cost": _money(row.get("cost")) or "—",
        })

    return {
        "calls": calls,
        "stat_rows": _stat_rows(totals),
        "details": _detail_rows(details),
        "cost": _money(cost) or "—",
        "origin": " · ".join(part for part in (provider_type, model) if part),
    }


def summarize_lifetime(rows: list[dict]) -> dict:
    """All-time totals from one row per model (the SQL sums them per model).

    Shares are of the token total across every model, and the bar behind a row
    is that share. `cost` only ever covers providers that report it.
    """
    totals = {key: 0 for key, _ in _TOKEN_ROWS}
    models: list[dict] = []
    calls = 0
    cost = None

    for row in rows:
        for key in totals:
            totals[key] += int(row.get(key) or 0)
        tokens = int(row.get("total_tokens") or 0) or (
            int(row.get("prompt_tokens") or 0) + int(row.get("completion_tokens") or 0)
        )
        calls += int(row.get("calls") or 0)
        if row.get("cost") is not None:
            cost = (cost or 0.0) + float(row["cost"])
        models.append({
            "model": row.get("model_name") or "",
            "provider": row.get("provider_type") or "",
            "tokens": tokens,
            "tokens_label": f"{tokens:,}",
            "cost": _money(row.get("cost")) or "—",
        })

    grand = sum(model["tokens"] for model in models)
    for model in models:
        share = model["tokens"] / grand * 100 if grand else 0.0
        model["share"] = f"{share:.1f}"
        model["share_label"] = f"{share:.1f}%"

    return {
        "models": models,
        "stat_rows": _stat_rows(totals),
        "cost": _money(cost) or "—",
        "calls": calls,
    }
