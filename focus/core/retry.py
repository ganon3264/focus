"""Retry policy for provider requests.

Pure decision logic only — no I/O, no async, no event handling. The retry
*loop* lives in ``focus/routers/stream.py`` because it has to interleave with
SSE event yielding and per-tool-iteration state.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

_RATE_LIMIT_STATUSES = frozenset({429})

# Failure classes with no HTTP status code. ``on_timeout`` covers both real
# timeouts and connection-level failures, so both sets share one tuple.
_TIMEOUT_HINTS = (
    "timeout",
    "timed out",
    "deadline exceeded",
    "deadlineexceeded",
    "apitimeouterror",
    "connecterror",
    "connectionerror",
    "connection reset",
    "connection aborted",
    "connection refused",
    "apiconnectionerror",
    "remoteprotocolerror",
    "serverdisconnectederror",
    "networkerror",
    "incomplete chunked read",
    "temporarily unavailable",
)

_RETRY_AFTER_PATTERNS = (
    re.compile(r"retry in ([0-9.]+)\s*s", re.IGNORECASE),
    re.compile(r"retry[_ ]?after[\"'\s:]+([0-9.]+)\s*s", re.IGNORECASE),
    re.compile(r"try again in ([0-9.]+)\s*s", re.IGNORECASE),
)


@dataclass(frozen=True)
class Classification:
    """How a provider exception should be treated.

    ``kind`` is one of ``rate_limit``, ``server``, ``timeout``, ``auth``,
    ``bad_request``, ``payment``, ``unknown``. Explicit user-supplied status
    codes are matched separately and can extend the retry set with no denylist.
    """

    kind: str
    status: int | None = None
    retry_after: float | None = None


@dataclass
class RetryConfig:
    enabled: bool = True
    max_retries: int = 5
    base_delay: float = 2.0
    max_delay: float = 20.0
    on_rate_limit: bool = False
    on_server_error: bool = True
    on_timeout: bool = True
    extra_statuses: tuple[int, ...] = field(default_factory=tuple)
    # Not user-exposed: safety rails against retry loops outliving a generation.
    hard_cap: float = 120.0
    total_budget: float = 180.0

    @classmethod
    def from_params(cls, params: dict[str, Any] | None) -> RetryConfig:
        """Build a config from a provider's ``params`` dict.

        A missing or malformed ``params["retry"]`` yields all defaults, so
        providers created before this feature (and absent keys generally) keep
        working and inherit future default changes.
        """
        raw = (params or {}).get("retry")
        if not isinstance(raw, dict):
            return cls()
        defaults = cls()
        return cls(
            enabled=_as_bool(raw.get("enabled"), defaults.enabled),
            max_retries=_clamp_int(raw.get("max_retries"), defaults.max_retries, 0, 10),
            base_delay=_clamp_float(raw.get("base_delay"), defaults.base_delay, 0.0, 60.0),
            max_delay=_clamp_float(raw.get("max_delay"), defaults.max_delay, 0.0, 300.0),
            on_rate_limit=_as_bool(raw.get("on_rate_limit"), defaults.on_rate_limit),
            on_server_error=_as_bool(raw.get("on_server_error"), defaults.on_server_error),
            on_timeout=_as_bool(raw.get("on_timeout"), defaults.on_timeout),
            extra_statuses=coerce_statuses(raw.get("extra_statuses")),
        )


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if value is None:
        return default
    return bool(value)


def _clamp_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _clamp_float(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def coerce_statuses(value: Any) -> tuple[int, ...]:
    """Normalize a status-code selection to a sorted tuple of valid ints.

    Accepts a list/tuple/set or a comma/space-separated string. Invalid and
    out-of-range tokens are dropped rather than raising.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        tokens: list[Any] = re.split(r"[,\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        tokens = list(value)
    else:
        tokens = [value]
    out: set[int] = set()
    for tok in tokens:
        if tok is None or tok == "":
            continue
        try:
            code = int(tok)
        except (TypeError, ValueError):
            continue
        if 100 <= code <= 599:
            out.add(code)
    return tuple(sorted(out))


def _extract_status(exc: Exception) -> int | None:
    for attr in ("status_code", "code"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
    resp = getattr(exc, "response", None)
    if resp is not None:
        val = getattr(resp, "status_code", None)
        if isinstance(val, int):
            return val
    return None


def _parse_retry_after_header(raw: Any) -> float | None:
    if not raw:
        return None
    try:
        secs = float(raw)
        return secs if secs >= 0 else None
    except (TypeError, ValueError):
        pass
    try:
        dt = parsedate_to_datetime(str(raw))
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = (dt - datetime.now(UTC)).total_seconds()
    return delta if delta > 0 else 0.0


def _extract_retry_after(exc: Exception) -> float | None:
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) if resp is not None else None
    if headers is not None:
        try:
            parsed = _parse_retry_after_header(headers.get("retry-after"))
        except (AttributeError, TypeError):
            parsed = None
        if parsed is not None:
            return parsed
    # Google reports the wait in the error message ("Please retry in 23.5s").
    msg = str(exc)
    for pattern in _RETRY_AFTER_PATTERNS:
        match = pattern.search(msg)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def classify(exc: Exception) -> Classification:
    """Classify a provider exception without importing any provider SDK."""
    status = _extract_status(exc)
    retry_after = _extract_retry_after(exc)
    if status is not None:
        if status in _RATE_LIMIT_STATUSES:
            return Classification("rate_limit", status, retry_after)
        if 500 <= status <= 599:
            return Classification("server", status, retry_after)
        if status == 402:
            return Classification("payment", status, retry_after)
        if status in (401, 403):
            return Classification("auth", status, retry_after)
        if status in (400, 404, 409, 422):
            return Classification("bad_request", status, retry_after)
        return Classification("unknown", status, retry_after)

    haystack = f"{type(exc).__name__} {exc}".lower()
    if any(hint in haystack for hint in _TIMEOUT_HINTS):
        return Classification("timeout", None, retry_after)
    return Classification("unknown", None, retry_after)


def is_retryable(cfg: RetryConfig, cls: Classification) -> bool:
    """Decide whether *cls* should be retried under *cfg*.

    Explicit status codes are matched first and bypass the class flags
    entirely — the user owns that decision, there is no denylist.
    """
    if not cfg.enabled:
        return False
    if cls.status is not None and cls.status in cfg.extra_statuses:
        return True
    if cls.kind == "rate_limit":
        return cfg.on_rate_limit
    if cls.kind == "server":
        return cfg.on_server_error
    if cls.kind == "timeout":
        return cfg.on_timeout
    return False


def delay_for(attempt: int, cfg: RetryConfig, retry_after: float | None = None) -> float:
    """Seconds to wait before retry number *attempt* (0-based).

    Exponential backoff with *equal jitter* (half fixed, half random) so a
    retry can never fire immediately. A server-provided ``Retry-After`` is
    always honored: we never retry earlier than the server asked.
    """
    backoff = min(cfg.max_delay, cfg.base_delay * (2 ** attempt))
    jittered = backoff / 2 + random.uniform(0, backoff / 2)
    if retry_after is not None:
        return max(jittered, retry_after)
    return jittered
