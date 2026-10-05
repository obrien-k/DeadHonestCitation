"""core/legitimacy.py: the live-copy gate (ADR-0001), against a real local HTTP site."""

import pytest
from bs4 import BeautifulSoup
from conftest import LiveSite

from dead_honest_citation.core.legitimacy import Legitimacy, assess_live
from dead_honest_citation.network.polite import polite_get


def _assess(url: str) -> Legitimacy:
    resp = polite_get(url, raise_on_error=False, retries=1)
    return assess_live(url, resp, BeautifulSoup(resp.text, "html.parser"))


def test_live_cms_article_passes(live_site: LiveSite) -> None:
    v = _assess(f"{live_site.url}/2009/03/signal-over-noise/")
    assert v.ok
    assert v.platform == "wordpress"
    assert v.hops == 0
    assert v.reason == "HTTP 200, CMS: wordpress"


def test_one_same_site_redirect_passes(live_site: LiveSite) -> None:
    v = _assess(f"{live_site.url}/old-link")
    assert v.ok
    assert v.hops == 1
    assert v.final_url == f"{live_site.url}/2009/03/signal-over-noise/"
    assert "1 redirect(s)" in v.reason


@pytest.mark.parametrize(
    "path,reason",
    [
        ("/gone", "HTTP 404"),
        ("/moved", "redirected to the homepage"),
        ("/chain", "redirect chain of 5 hops (max 3)"),
        ("/soft404", "soft 404 (not-found page served as 200)"),
        ("/parked", "parked domain (sedoparking.com)"),
        ("/plain", "no CMS recognized"),
    ],
)
def test_illegitimate_live_copies_fail(live_site: LiveSite, path: str, reason: str) -> None:
    v = _assess(f"{live_site.url}{path}")
    assert not v.ok
    assert v.reason == reason


def test_offsite_redirect_fails(live_site: LiveSite) -> None:
    v = _assess(f"{live_site.url}/offsite")
    assert not v.ok
    assert v.reason == "redirected off-site to localhost"
