"""
A small, shared, polite HTTP layer. Centralizes the rate-limit policy so the whole
toolchain is a good citizen toward archive.org (a donor-funded nonprofit) and any
other host: a global minimum interval between requests, Retry-After handling, and
exponential backoff. Sequential by design, so concurrency is naturally bounded at 1.

Tunable via the environment:
  DHC_MIN_INTERVAL   seconds between requests (default 0.5)
  DHC_MAX_RETRIES    attempts before giving up (default 4)
"""

import os
import time

import requests

USER_AGENT = "dead-honest-citation/0.3 (+https://github.com/obrien-k/DeadHonestCitation)"
HEADERS = {"User-Agent": USER_AGENT}

MIN_INTERVAL = float(os.environ.get("DHC_MIN_INTERVAL", "0.5"))
MAX_RETRIES = int(os.environ.get("DHC_MAX_RETRIES", "4"))
MAX_BACKOFF = 60.0

# Module-global on purpose: one throttle clock per process, however many callers.
_last_request = 0.0


def _throttle():
    """Sleep just enough to keep at least MIN_INTERVAL between requests."""
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _backoff(attempt):
    return min(2.0**attempt, MAX_BACKOFF)


def _retry_after(resp, attempt):
    """Honor a Retry-After header (seconds) when present, else exponential backoff."""
    value = resp.headers.get("Retry-After")
    if value:
        try:
            return min(float(value), MAX_BACKOFF * 2)
        except ValueError:
            pass
    return _backoff(attempt)


def polite_get(
    url,
    *,
    method="GET",
    params=None,
    headers=None,
    timeout=20,
    allow_redirects=True,
    retries=None,
    raise_on_error=True,
):
    """A rate-limited request with Retry-After handling and exponential backoff.

    Returns the Response; with raise_on_error it raises requests.RequestException after
    the final attempt (and on any 4xx/5xx). 429/503 are retried per Retry-After and
    connection errors back off exponentially, so a transient throttle/refusal degrades
    gracefully. Set raise_on_error=False when a non-2xx is a valid answer (e.g. a
    liveness probe where 404 means "not live", not "retry")."""
    retries = retries or MAX_RETRIES
    hdrs = headers or HEADERS
    last_exc = None
    for attempt in range(retries):
        _throttle()
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
                wait = _retry_after(resp, attempt)
                if attempt < retries - 1:
                    print(f"  ⏳ {resp.status_code} from server; backing off {wait:.0f}s…")
                    time.sleep(wait)
                    continue
            if raise_on_error:
                resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries - 1:
                wait = _backoff(attempt)
                print(f"  Retrying ({attempt + 1}/{retries - 1}) in {wait:.0f}s…")
                time.sleep(wait)
    raise last_exc or requests.RequestException(f"request failed: {url}")
