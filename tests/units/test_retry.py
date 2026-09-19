"""Unit tests for the retry policy in ``focus/core/retry.py``.

Pure policy only: config parsing, exception classification, retry decisions,
and delay math. The orchestration loop is covered by the API stream tests.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from focus.core.retry import (
    Classification,
    RetryConfig,
    classify,
    coerce_statuses,
    delay_for,
    is_retryable,
)
from focus.routers.stream import _sleep_or_stop


class FakeResponse:
    def __init__(self, retry_after=None, status_code=429):
        self.status_code = status_code
        self.headers = {"retry-after": retry_after} if retry_after is not None else {}


class HTTPError(Exception):
    def __init__(self, status, retry_after=None):
        super().__init__(f"HTTP {status}")
        self.status_code = status
        self.response = FakeResponse(retry_after, status) if retry_after is not None else None


class StatusCodeError(Exception):
    """Mimics google.genai.errors.APIError, which exposes ``.code``."""

    def __init__(self, code, message="boom"):
        super().__init__(message)
        self.code = code


class TestFromParams:
    def test_defaults_when_missing(self):
        cfg = RetryConfig.from_params({})
        assert cfg.enabled is True
        assert cfg.max_retries == 3
        assert cfg.base_delay == 2.0
        assert cfg.max_delay == 30.0
        assert cfg.on_rate_limit and cfg.on_server_error and cfg.on_timeout
        assert cfg.extra_statuses == ()

    def test_defaults_when_retry_not_a_dict(self):
        assert RetryConfig.from_params({"retry": "nope"}) == RetryConfig()

    def test_partial_override(self):
        cfg = RetryConfig.from_params({"retry": {"enabled": False, "max_retries": 5}})
        assert cfg.enabled is False
        assert cfg.max_retries == 5
        assert cfg.base_delay == 2.0  # untouched default

    def test_values_are_clamped(self):
        cfg = RetryConfig.from_params({
            "retry": {"max_retries": 999, "base_delay": -5, "max_delay": 10_000},
        })
        assert cfg.max_retries == 10
        assert cfg.base_delay == 0.0
        assert cfg.max_delay == 300.0

    def test_string_booleans(self):
        cfg = RetryConfig.from_params({"retry": {"enabled": "false", "on_timeout": "yes"}})
        assert cfg.enabled is False
        assert cfg.on_timeout is True


class TestCoerceStatuses:
    def test_none_and_empty(self):
        assert coerce_statuses(None) == ()
        assert coerce_statuses("") == ()
        assert coerce_statuses([]) == ()

    def test_string(self):
        assert coerce_statuses("503, 425  418") == (418, 425, 503)

    def test_list_dedupes_and_sorts(self):
        assert coerce_statuses([503, "503", 425, 425]) == (425, 503)

    def test_drops_invalid_and_out_of_range(self):
        assert coerce_statuses(["nope", 99, 600, 200]) == (200,)


class TestClassify:
    def test_rate_limit(self):
        assert classify(HTTPError(429)).kind == "rate_limit"

    def test_server_errors(self):
        for code in (500, 502, 503, 504, 529, 599):
            assert classify(HTTPError(code)).kind == "server"

    def test_auth_and_bad_request_and_payment(self):
        assert classify(HTTPError(401)).kind == "auth"
        assert classify(HTTPError(403)).kind == "auth"
        assert classify(HTTPError(400)).kind == "bad_request"
        assert classify(HTTPError(422)).kind == "bad_request"
        assert classify(HTTPError(402)).kind == "payment"

    def test_unknown_status(self):
        assert classify(HTTPError(418)).kind == "unknown"

    def test_status_from_code_attribute(self):
        assert classify(StatusCodeError(429)).status == 429
        assert classify(StatusCodeError(429)).kind == "rate_limit"

    def test_timeout_by_name(self):
        class APITimeoutError(Exception):
            pass

        assert classify(APITimeoutError("gone")).kind == "timeout"

    def test_connection_by_name(self):
        class ConnectError(Exception):
            pass

        assert classify(ConnectError("refused")).kind == "timeout"

    def test_transport_by_message(self):
        assert classify(RuntimeError("Connection reset by peer")).kind == "timeout"
        assert classify(RuntimeError("read timed out")).kind == "timeout"

    def test_plain_error_is_unknown(self):
        assert classify(ValueError("bad")).kind == "unknown"

    def test_retry_after_header_seconds(self):
        assert classify(HTTPError(429, retry_after="23")).retry_after == 23.0

    def test_retry_after_header_http_date(self):
        future = datetime.now(UTC) + timedelta(seconds=30)
        cls = classify(HTTPError(429, retry_after=format_datetime(future, usegmt=True)))
        assert cls.retry_after is not None
        assert 25 <= cls.retry_after <= 35

    def test_retry_after_from_google_message(self):
        err = StatusCodeError(429, "Resource exhausted. Please retry in 23.5s.")
        assert classify(err).retry_after == 23.5


class TestIsRetryable:
    def test_class_flags(self):
        cfg = RetryConfig()
        assert is_retryable(cfg, Classification("rate_limit")) is True
        assert is_retryable(cfg, Classification("server")) is True
        assert is_retryable(cfg, Classification("timeout")) is True
        assert is_retryable(cfg, Classification("auth")) is False
        assert is_retryable(cfg, Classification("unknown")) is False

    def test_flags_can_be_disabled(self):
        cfg = RetryConfig(on_rate_limit=False, on_server_error=False, on_timeout=False)
        assert is_retryable(cfg, Classification("rate_limit")) is False
        assert is_retryable(cfg, Classification("server")) is False
        assert is_retryable(cfg, Classification("timeout")) is False

    def test_extra_statuses_extend_defaults(self):
        cfg = RetryConfig(extra_statuses=(418,))
        assert is_retryable(cfg, Classification("unknown", status=418)) is True

    def test_extra_statuses_can_resurrect_denied_classes(self):
        cfg = RetryConfig(extra_statuses=(401,))
        assert is_retryable(cfg, Classification("auth", status=401)) is True

    def test_disabled_short_circuits_everything(self):
        cfg = RetryConfig(enabled=False, extra_statuses=(429,))
        assert is_retryable(cfg, Classification("rate_limit", status=429)) is False


class TestDelayFor:
    def test_backoff_within_bounds(self):
        cfg = RetryConfig(base_delay=2.0, max_delay=30.0)
        for attempt in range(6):
            delay = delay_for(attempt, cfg)
            assert 0 <= delay <= cfg.max_delay
            # equal jitter means at least half the exponential step
            expected = min(cfg.max_delay, cfg.base_delay * (2 ** attempt))
            assert delay >= expected / 2

    def test_zero_base_gives_zero(self):
        assert delay_for(3, RetryConfig(base_delay=0.0, max_delay=30.0)) == 0.0

    def test_retry_after_is_a_floor(self):
        cfg = RetryConfig(base_delay=1.0, max_delay=5.0)
        assert delay_for(0, cfg, retry_after=60.0) == 60.0

    def test_retry_after_not_lower_than_backoff(self):
        cfg = RetryConfig(base_delay=10.0, max_delay=30.0)
        # base 10s, equal jitter -> >= 5s; retry_after 0 must not pull it down
        assert delay_for(0, cfg, retry_after=0.0) >= 5.0


class TestSleepOrStop:
    async def test_sleeps_and_returns_false(self):
        assert await _sleep_or_stop(0.01, None) is False

    async def test_returns_true_when_stop_fires(self):
        event = asyncio.Event()

        async def set_soon():
            await asyncio.sleep(0.01)
            event.set()

        asyncio.create_task(set_soon())
        assert await _sleep_or_stop(5.0, event) is True

    async def test_returns_false_when_timeout_elapses_first(self):
        assert await _sleep_or_stop(0.01, asyncio.Event()) is False
