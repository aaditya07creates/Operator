"""Client-side rate limiting for LLM API calls.

Mirrors the server's limits locally so OPERATOR never slams into them:

- **Pacing**: a minimum interval between API calls turns the agentic loop's
  bursts (up to 9 back-to-back calls per task) into a smooth queue. Mistral's
  free Experiment tier enforces a low requests-per-second cap, so calls are
  spaced by Config.LLM_MIN_INTERVAL seconds (default 1.1).
- **429 recovery**: if the server still rate-limits us (tokens-per-minute is
  enforced independently of request rate), the call is retried with
  exponential backoff, honoring a Retry-After header when the SDK exposes
  one. The caller just sees a slower reply, never an error — unless every
  retry is exhausted.

Thread-safe: provider calls run in asyncio.to_thread workers, so the limiter
serializes turn-taking with a lock. Sleeping here blocks only that worker
thread, never the event loop.
"""

import re
import threading
import time
from typing import Callable, Optional

from config import Config
from logger_config import op_logger


def _is_rate_limit_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "too many requests" in text \
        or "capacity exceeded" in text or "requests rate limit exceeded" in text


def _retry_after_seconds(exc: Exception) -> Optional[float]:
    """Pull a server-suggested wait out of the exception, if available."""
    raw = getattr(exc, "raw_response", None)
    headers = getattr(raw, "headers", None)
    if headers:
        value = headers.get("retry-after") or headers.get("Retry-After")
        if value:
            try:
                return float(value)
            except ValueError:
                pass
    # Some SDKs embed it in the message ("retry after 3 seconds")
    match = re.search(r"retry.{0,10}?(\d+(?:\.\d+)?)\s*s", str(exc).lower())
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


class RateLimiter:
    """Paces calls to a minimum interval and retries 429s with backoff."""

    def __init__(self, min_interval: float = None, max_retries: int = None):
        self.min_interval = Config.LLM_MIN_INTERVAL if min_interval is None else min_interval
        self.max_retries = Config.LLM_MAX_RETRIES if max_retries is None else max_retries
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def _wait_turn(self):
        """Block until this thread's turn; reserve the next slot atomically."""
        with self._lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(self._next_slot, now) + self.min_interval
        if wait > 0:
            time.sleep(wait)

    def call(self, fn: Callable, provider: str = "LLM",
             max_retries: Optional[int] = None):
        """Run fn() paced; on 429, back off and retry (2s, 4s, 8s, 16s...)."""
        if max_retries is None:
            max_retries = self.max_retries
        last_exc = None
        for attempt in range(max_retries + 1):
            self._wait_turn()
            try:
                return fn()
            except Exception as e:
                if not _is_rate_limit_error(e):
                    raise
                last_exc = e
                if attempt >= max_retries:
                    break
                delay = _retry_after_seconds(e) or (2.0 * (2 ** attempt))
                delay = min(delay, 30.0)
                op_logger.logger.warning(
                    f"{provider} rate limited (attempt {attempt + 1}/"
                    f"{max_retries}); retrying in {delay:.0f}s"
                )
                time.sleep(delay)
        raise last_exc


# One shared limiter for the process — only one provider is active per
# session, and a single queue is exactly how the server sees us anyway.
limiter = RateLimiter()
