"""RateLimiter: pacing, 429 backoff/retry, retry-after, give-up."""

import time

import pytest

from rate_limiter import RateLimiter, _is_rate_limit_error, _retry_after_seconds


class Fake429(Exception):
    status_code = 429


def test_paces_calls():
    rl = RateLimiter(min_interval=0.12, max_retries=0)
    start = time.monotonic()
    rl.call(lambda: "a")
    rl.call(lambda: "b")
    rl.call(lambda: "c")
    elapsed = time.monotonic() - start
    # Windows timer granularity can shave ~15ms off each sleep; 0.2 still
    # proves two enforced gaps between three calls.
    assert elapsed >= 0.2, f"three calls should span ~2 intervals, took {elapsed:.3f}s"


def test_retries_429_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    rl = RateLimiter(min_interval=0.0, max_retries=3)

    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise Fake429("429 too many requests")
        return "ok"

    assert rl.call(flaky) == "ok"
    assert attempts["n"] == 3
    # Exponential backoff: 2s then 4s
    backoffs = [s for s in sleeps if s >= 1]
    assert backoffs == [2.0, 4.0]


def test_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    rl = RateLimiter(min_interval=0.0, max_retries=2)

    def always_limited():
        raise Fake429("rate limit exceeded")

    with pytest.raises(Fake429):
        rl.call(always_limited)


def test_non_429_raises_immediately():
    rl = RateLimiter(min_interval=0.0, max_retries=5)
    attempts = {"n": 0}

    def broken():
        attempts["n"] += 1
        raise ValueError("bad request")

    with pytest.raises(ValueError):
        rl.call(broken)
    assert attempts["n"] == 1, "non-rate-limit errors must not be retried"


def test_rate_limit_detection():
    assert _is_rate_limit_error(Fake429("x"))
    assert _is_rate_limit_error(Exception("HTTP 429"))
    assert _is_rate_limit_error(Exception("Requests rate limit exceeded"))
    assert not _is_rate_limit_error(Exception("connection refused"))


def test_retry_after_parsing():
    class WithHeader(Exception):
        class raw_response:
            headers = {"retry-after": "7"}

    assert _retry_after_seconds(WithHeader("x")) == 7.0
    assert _retry_after_seconds(Exception("please retry after 3 seconds")) == 3.0
    assert _retry_after_seconds(Exception("no hint here")) is None


def test_mistral_falls_back_to_small_on_429(monkeypatch):
    """When the primary model's window is saturated, the reply completes on
    the fallback model instead of raising."""
    from types import SimpleNamespace

    import rate_limiter
    monkeypatch.setattr(rate_limiter.time, "sleep", lambda s: None)

    from config import Config
    from llm_providers import MistralProvider

    calls = []

    def fake_complete(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == Config.MISTRAL_MODEL:
            raise Fake429("429 rate limit exceeded")
        msg = SimpleNamespace(content="fallback says hi", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    p = MistralProvider(api_key="test")
    p.client = SimpleNamespace(chat=SimpleNamespace(complete=fake_complete))
    p.add_system_message("sys")

    r = p.chat(user_message="hello")
    assert r.text == "fallback says hi"
    assert Config.MISTRAL_FALLBACK_MODEL in calls
    # Primary was tried (with short retry) before falling back
    assert calls.count(Config.MISTRAL_MODEL) >= 1


def test_honors_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    rl = RateLimiter(min_interval=0.0, max_retries=1)

    attempts = {"n": 0}

    class Hinted(Exception):
        class raw_response:
            headers = {"retry-after": "5"}

        status_code = 429

    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise Hinted("429")
        return "ok"

    assert rl.call(flaky) == "ok"
    assert 5.0 in sleeps, "server-suggested retry-after should be used"
