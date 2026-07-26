"""network/polite.py: PoliteSession retry/backoff policy, with mocked HTTP."""

import pytest
import requests
import responses

from dead_honest_citation.exceptions import WaybackRateLimitError
from dead_honest_citation.network import polite as polite_mod
from dead_honest_citation.network.polite import polite_get

URL = "https://web.archive.org/cdx/search/cdx"


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backoff/Retry-After waits use real time.sleep; stub it so retries are instant."""
    monkeypatch.setattr(polite_mod.time, "sleep", lambda seconds: None)


# --- 429 with Retry-After: retried then succeeds ------------------------------


@responses.activate
def test_429_with_retry_after_is_retried_then_succeeds() -> None:
    responses.add(responses.GET, URL, status=429, headers={"Retry-After": "0"})
    responses.add(responses.GET, URL, status=200, body="ok")
    resp = polite_get(URL, retries=2)
    assert resp.status_code == 200
    assert resp.text == "ok"
    assert len(responses.calls) == 2


# --- retries exhaust -> raises WaybackRateLimitError --------------------------


@responses.activate
def test_429_exhausting_retries_raises_wayback_rate_limit_error() -> None:
    for _ in range(3):
        responses.add(responses.GET, URL, status=429, headers={"Retry-After": "1"})
    with pytest.raises(WaybackRateLimitError) as excinfo:
        polite_get(URL, retries=3)
    assert excinfo.value.retry_after == 1.0
    assert len(responses.calls) == 3


@responses.activate
def test_503_exhausting_retries_raises_wayback_rate_limit_error() -> None:
    for _ in range(2):
        responses.add(responses.GET, URL, status=503)
    with pytest.raises(WaybackRateLimitError):
        polite_get(URL, retries=2)


# --- raise_on_error=False returns the 404 -------------------------------------


@responses.activate
def test_raise_on_error_false_returns_404_response() -> None:
    responses.add(responses.GET, URL, status=404)
    resp = polite_get(URL, raise_on_error=False)
    assert resp.status_code == 404


@responses.activate
def test_raise_on_error_true_raises_for_404() -> None:
    responses.add(responses.GET, URL, status=404)
    with pytest.raises(requests.HTTPError):
        polite_get(URL, retries=2, raise_on_error=True)


@responses.activate
def test_raise_on_error_false_still_returns_final_429_response() -> None:
    # A liveness probe (raise_on_error=False) gets the final response, not an
    # exception, even when the retry budget on a 429 is spent.
    for _ in range(2):
        responses.add(responses.GET, URL, status=429)
    resp = polite_get(URL, retries=2, raise_on_error=False)
    assert resp.status_code == 429


# --- version surfaces derive from the manifest, never hand-kept ---------------


def test_user_agent_derives_from_package_version() -> None:
    """The polite UA must track the manifest.

    It silently said 0.3 after the v0.4.0 bump — three hand-maintained literals
    (pyproject, __init__, this UA) with nothing keeping them honest.
    """
    from dead_honest_citation import __version__
    from dead_honest_citation.network.polite import USER_AGENT

    major_minor = ".".join(__version__.split(".")[:2])
    assert USER_AGENT.startswith(f"dead-honest-citation/{major_minor} ")


def test_package_version_matches_installed_distribution() -> None:
    from importlib.metadata import version

    from dead_honest_citation import __version__

    assert __version__ == version("dead-honest-citation")
