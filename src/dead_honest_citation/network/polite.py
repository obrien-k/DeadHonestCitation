"""
A small, shared, polite HTTP layer. Centralizes the rate-limit policy so the whole
toolchain is a good citizen toward archive.org (a donor-funded nonprofit) and any
other host: a global minimum interval between requests, Retry-After handling, and
exponential backoff. Sequential by design, so concurrency is naturally bounded at 1.

The policy lives on a `PoliteSession`; one module-level instance (`_session`) is
shared process-wide so the throttle clock survives across callers. `polite_get`
is a thin wrapper delegating to it — the public API is unchanged.

Tunable via the environment:
  DHC_MIN_INTERVAL   seconds between requests (default 0.5)
  DHC_MAX_RETRIES    attempts before giving up (default 4)
"""

import os
import time
from typing import Any

import requests

from ..exceptions import WaybackRateLimitError
from ..ui import log, warn

USER_AGENT = "dead-honest-citation/0.4 (+https://github.com/obrien-k/DeadHonestCitation)"
HEADERS = {"User-Agent": USER_AGENT}

MIN_INTERVAL = float(os.environ.get("DHC_MIN_INTERVAL", "0.5"))
MAX_RETRIES = int(os.environ.get("DHC_MAX_RETRIES", "4"))
MAX_BACKOFF = 60.0


class PoliteSession:
    """Process-wide rate limiter around `requests`.

    Holds the single throttle clock (`_last_request`) and the retry policy. The
    module keeps one shared instance so every caller throttles against the same
    clock; env tunables set the defaults but per-call overrides still win.
    """

    def __init__(self, min_interval: float = MIN_INTERVAL, max_retries: int = MAX_RETRIES) -> None:
        self.min_interval = min_interval
        self.max_retries = max_retries
        # One throttle clock per instance (hence per process).
        self._last_request = 0.0

    def _throttle(self) -> None:
        """Sleep just enough to keep at least min_interval between requests."""
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(2.0**attempt, MAX_BACKOFF)

    @staticmethod
    def _retry_after_seconds(resp: requests.Response) -> float | None:
        """The Retry-After header as seconds, if present and numeric."""
        value = resp.headers.get("Retry-After")
        if value:
            try:
                return min(float(value), MAX_BACKOFF * 2)
            except ValueError:
                pass
        return None

    def _retry_after(self, resp: requests.Response, attempt: int) -> float:
        """Honor a Retry-After header (seconds) when present, else exponential backoff."""
        seconds = self._retry_after_seconds(resp)
        return seconds if seconds is not None else self._backoff(attempt)

    def get(
        self,
        url: str,
        *,
        method: str = "GET",
        params: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 20,
        allow_redirects: bool = True,
        retries: int | None = None,
        raise_on_error: bool = True,
    ) -> requests.Response:
        """A rate-limited request with Retry-After handling and exponential backoff.

        429/503 are retried per Retry-After and connection errors back off
        exponentially, so a transient throttle/refusal degrades gracefully.

        Args:
            url: The URL to request.
            method: HTTP method (default GET).
            params: Query parameters, as accepted by requests.
            headers: Request headers (defaults to the polite User-Agent).
            timeout: Per-attempt timeout in seconds (always set, never unbounded).
            allow_redirects: Follow redirects (default True).
            retries: Attempts before giving up (default DHC_MAX_RETRIES).
            raise_on_error: Raise on any 4xx/5xx and after the final attempt. Set
                False when a non-2xx is a valid answer (e.g. a liveness probe where
                404 means "not live", not "retry").

        Returns:
            The requests.Response.

        Raises:
            WaybackRateLimitError: When 429/503 persists through the retry budget
                and raise_on_error is set.
            requests.RequestException: Any other transport/HTTP failure after the
                final attempt (and on any 4xx/5xx when raise_on_error is set).
        """
        retries = retries or self.max_retries
        hdrs = headers or HEADERS
        last_exc: requests.RequestException | None = None
        for attempt in range(retries):
            self._throttle()
            log.debug("%s %s (attempt %d/%d)", method, url, attempt + 1, retries)
            try:
                resp = requests.request(
                    method,
                    url,
                    params=params,
                    headers=hdrs,
                    timeout=timeout,
                    allow_redirects=allow_redirects,
                )
                if resp.status_code in (429, 503):
                    if attempt < retries - 1:
                        wait = self._retry_after(resp, attempt)
                        warn(f"  ⏳ {resp.status_code} from server; backing off {wait:.0f}s…")
                        time.sleep(wait)
                        continue
                    # Retry budget spent on a rate-limit. Raise the typed error only
                    # when the caller wants errors raised; a liveness probe
                    # (raise_on_error=False) still gets the final response back.
                    if raise_on_error:
                        raise WaybackRateLimitError(
                            f"{resp.status_code} after {retries} attempts: {url}",
                            retry_after=self._retry_after_seconds(resp),
                            response=resp,
                        )
                    return resp
                if raise_on_error:
                    resp.raise_for_status()
                return resp
            except WaybackRateLimitError:
                raise
            except requests.RequestException as e:
                last_exc = e
                if attempt < retries - 1:
                    wait = self._backoff(attempt)
                    warn(f"  Retrying ({attempt + 1}/{retries - 1}) in {wait:.0f}s…")
                    time.sleep(wait)
        raise last_exc or requests.RequestException(f"request failed: {url}")


# Module-global on purpose: one throttle clock per process, however many callers.
_session = PoliteSession()


def polite_get(
    url: str,
    *,
    method: str = "GET",
    params: Any = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20,
    allow_redirects: bool = True,
    retries: int | None = None,
    raise_on_error: bool = True,
) -> requests.Response:
    """Thin wrapper delegating to the shared PoliteSession (public API unchanged)."""
    return _session.get(
        url,
        method=method,
        params=params,
        headers=headers,
        timeout=timeout,
        allow_redirects=allow_redirects,
        retries=retries,
        raise_on_error=raise_on_error,
    )
