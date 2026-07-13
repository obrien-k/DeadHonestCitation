"""
The package exception hierarchy.

These are raised at the failure sites in the network and pipeline layers and
caught at the orchestration boundary (`process_url` / `process_markdown`), which
turns each into an `Outcome` — so a batch never dies on one bad source and
`runlog.jsonl` gets an actionable reason instead of a stack trace.

`WaybackRateLimitError` also subclasses `requests.RequestException` on purpose:
the discovery code paths (`cli/discover.py`) catch `requests.RequestException`
around `polite_get`, and a rate-limit exhaustion must stay catchable there while
still being a first-class `FetchError` for the pipeline boundary.
"""

import requests


class DHCError(Exception):
    """Base for every error this package raises deliberately."""


class FetchError(DHCError):
    """A source could not be loaded (network failure, unreadable file, …)."""


class WaybackRateLimitError(FetchError, requests.RequestException):
    """429/503 persisted until the retry budget was exhausted.

    Carries the last-seen `Retry-After` (seconds) when the server sent one.
    Dual-typed as a `requests.RequestException` so discovery callers that catch
    that keep working (see module docstring).
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        response: requests.Response | None = None,
    ) -> None:
        # RequestException.__init__ handles args + response/request bookkeeping.
        requests.RequestException.__init__(self, message, response=response)
        self.retry_after = retry_after


class PlatformDetectError(DHCError):
    """No input adapter recognized the page and none was forced."""


class ContentNotFoundError(DHCError):
    """The page loaded but no article/thread body could be located."""


class EmitError(DHCError):
    """The output target failed to write the converted result."""
