"""
The live-copy legitimacy gate (ADR-0001).

A live copy is the best source a citation can have, but only if it is really the
page: not a 404 or a CMS's "page not found" template, not a parked domain, and not
the end of a redirect chain that dumped the reader on a homepage or another site.
assess_live() decides that from the response DHC already fetched (no second
request), and only a page that passes earns a photo-record on its citation.

Following a publisher's redirects to *find* a moved page is out of scope: the gate
judges the URL it was given, it never searches.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ..adapters import detect_platform

# Redirect hops tolerated before the chain counts as "redirect hell". http→https
# and a trailing-slash or www hop are normal; a long chain is a publisher's
# migration map, which is not ours to walk.
MAX_REDIRECTS = 3

# Parked-domain fingerprints: parking/marketplace providers in the markup, and the
# for-sale copy they serve. Matched case-insensitively against the raw HTML.
PARKING_MARKERS = (
    "sedoparking.com",
    "parkingcrew.net",
    "bodis.com",
    "above.com/marketplace",
    "dan.com/buy-domain",
    "afternic.com",
    "hugedomains.com",
    "parklogic",
    "this domain is for sale",
    "this domain may be for sale",
    "buy this domain",
    "domain is parked",
)

# Soft 404: a 200 whose page is a CMS's not-found template.
SOFT_404_RE = re.compile(r"\b(page not found|404 not found|nothing (was )?found|error 404)\b", re.I)


@dataclass(frozen=True)
class Legitimacy:
    """The gate's verdict on one live response.

    Attributes:
        ok: True only when every check passed.
        reason: Why it failed, or a one-line summary of why it passed.
        final_url: Where the redirect chain ended.
        hops: Number of redirects followed.
        platform: The recognized CMS, or None.
    """

    ok: bool
    reason: str
    final_url: str
    hops: int
    platform: str | None


def _host(url: str) -> str:
    """Hostname without a leading www., lowercased — the unit "same site" compares."""
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def _is_root(url: str) -> bool:
    return urlparse(url).path in ("", "/")


def assess_live(url: str, resp: requests.Response, soup: BeautifulSoup) -> Legitimacy:
    """Judge whether a fetched live page is the real article (ADR-0001).

    Checks, in order: HTTP status (no 4xx/5xx), redirect chain (bounded, same host,
    not dumped on the homepage), soft 404 (the title/h1 is a not-found template),
    parked domain, and a recognized CMS (detect_platform(), never the generic
    fallback).

    Args:
        url: The URL as requested.
        resp: The final response (resp.history holds the redirect chain).
        soup: The parsed final page.

    Returns:
        The verdict; ok is True only when every check passed.
    """
    final_url = resp.url or url
    hops = len(resp.history)

    def fail(reason: str, platform: str | None = None) -> Legitimacy:
        return Legitimacy(False, reason, final_url, hops, platform)

    if resp.status_code >= 400:
        return fail(f"HTTP {resp.status_code}")
    if hops > MAX_REDIRECTS:
        return fail(f"redirect chain of {hops} hops (max {MAX_REDIRECTS})")
    if hops and _host(final_url) != _host(url):
        return fail(f"redirected off-site to {_host(final_url)}")
    if hops and _is_root(final_url) and not _is_root(url):
        return fail("redirected to the homepage")

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    heading = h1.get_text(" ", strip=True) if h1 else ""
    if SOFT_404_RE.search(title) or SOFT_404_RE.search(heading):
        return fail("soft 404 (not-found page served as 200)")

    html = resp.text.lower()
    marker = next((m for m in PARKING_MARKERS if m in html), None)
    if marker:
        return fail(f"parked domain ({marker})")

    platform = detect_platform(soup)
    if platform is None:
        return fail("no CMS recognized")

    via = f", {hops} redirect(s)" if hops else ""
    return Legitimacy(
        True, f"HTTP {resp.status_code}{via}, CMS: {platform}", final_url, hops, platform
    )
