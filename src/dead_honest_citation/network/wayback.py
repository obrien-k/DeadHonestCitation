"""
Wayback Machine interaction: snapshot-URL math (unwrap, raw-capture rewrites,
image candidates) and discovery (CDX enumeration, host recovery, Save Page Now).
"""

import re

import requests

from .polite import polite_get

# Wayback snapshot URLs carry an optional capture-mode suffix on the timestamp:
# im_ (raw image), if_ (raw iframe), js_, cs_, oe_, etc. Tolerate any of them.
WAYBACK_RE = re.compile(r"(?:https?://web\.archive\.org)?/web/\d+(?:[a-z]{2,3}_)?/(https?://.+)")

CDX_API = "https://web.archive.org/cdx/search/cdx"
SAVE_API = "https://web.archive.org/save/"

# Hosting platforms where a site's name becomes a subdomain — the candidates probed
# by host recovery when you remember a name but not the host.
COMMON_HOSTS = [
    "proboards.com",
    "blogspot.com",
    "wordpress.com",
    "tumblr.com",
    "livejournal.com",
    "neocities.org",
    "weebly.com",
    "wixsite.com",
    "github.io",
    "substack.com",
]


def unwrap_wayback(url: str) -> str:
    """The original URL inside a Wayback playback URL; non-Wayback URLs pass through."""
    m = WAYBACK_RE.match(url)
    return m.group(1) if m else url


def wayback_image_candidates(src: str) -> list[str]:
    """Ordered URLs to try when downloading an image src.

    For a Wayback URL: the archive's raw-image (`im_`) capture first, then the
    bare original. Non-Wayback srcs are returned as-is.
    """
    if src.startswith("/web/"):
        src = "https://web.archive.org" + src
    m = WAYBACK_RE.match(src)
    if not m:
        return [src]
    original = m.group(1)
    ts_match = re.match(r"(?:https?://web\.archive\.org)?/web/(\d+)", src)
    timestamp = ts_match.group(1) if ts_match else ""
    if timestamp:
        return [f"https://web.archive.org/web/{timestamp}im_/{original}", original]
    return [src, original]


def wayback_raw(url: str) -> str:
    """Rewrite a Wayback URL to its toolbar-free 'if_' capture so a screenshot frames the
    page itself, not the archive chrome. Non-Wayback URLs pass through unchanged."""
    m = re.match(r"(https?://web\.archive\.org/web/\d+)(/https?://.+)", url)
    return f"{m.group(1)}if_{m.group(2)}" if m else url


def discover(
    domain: str,
    contains: str | None = None,
    status: str | None = "200",
    mimetype: str | None = "text/html",
    newest: bool = False,
    timeout: float = 60,
) -> list[tuple[str, str]]:
    """Enumerate a domain's archived captures via the CDX API.

    One row per unique URL (CDX collapse=urlkey).

    Args:
        domain: Bare host to enumerate (no scheme).
        contains: Keep only URLs whose canonical key contains this (lowercased)
            substring — applied server-side as a CDX regex filter.
        status: HTTP status filter ("200" by default; None for any).
        mimetype: Mimetype filter (text/html by default; None for any).
        newest: Keep each URL's most recent capture instead of the earliest.
        timeout: Request timeout in seconds.

    Returns:
        (timestamp, original_url) pairs.
    """
    params = [
        ("url", f"{domain}*"),
        ("fl", "timestamp,original"),
        ("output", "text"),
        ("collapse", "urlkey"),
    ]
    if mimetype:
        params.append(("filter", f"mimetype:{mimetype}"))
    if status:
        params.append(("filter", f"statuscode:{status}"))
    if contains:
        # urlkey is already lowercased+canonicalized, so a lowercase substring
        # match is effectively case-insensitive.
        params.append(("filter", f"urlkey:.*{contains.lower()}.*"))
    if newest:
        # collapse keeps the first row of each group; reverse the scan so that
        # "first" is the most recent capture instead of the oldest.
        params.append(("reverse", "true"))

    resp = polite_get(CDX_API, params=params, timeout=timeout)

    rows = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line:
            continue
        timestamp, original = line.split(" ", 1)
        # Some captures store HTML-encoded ampersands in the URL (&amp;board=…);
        # decode so the playback URL resolves to the right capture.
        original = original.replace("&amp;", "&")
        rows.append((timestamp, original))
    return rows


def wayback_url(timestamp: str, original: str) -> str:
    """Build the playback URL the convert pipeline knows how to fetch and de-archive."""
    return f"https://web.archive.org/web/{timestamp}/{original}"


def host_latest_capture(host: str, timeout: float = 30) -> str | None:
    """Most recent Wayback capture timestamp for a host, or None if never archived."""
    params = [
        ("url", host),
        ("matchType", "host"),
        ("fl", "timestamp"),
        ("limit", "1"),
        ("reverse", "true"),
        ("output", "text"),
    ]
    try:
        resp = polite_get(CDX_API, params=params, timeout=timeout)
    except requests.RequestException:
        return None
    line = resp.text.strip()
    return line.split()[0] if line else None


def host_is_live(host: str, timeout: float = 10) -> bool:
    """True if the host responds today (tries HTTPS then HTTP)."""
    for scheme in ("https://", "http://"):
        try:
            resp = polite_get(scheme + host, method="HEAD", timeout=timeout, raise_on_error=False)
            if resp.status_code < 400:
                return True
        except requests.RequestException:
            continue
    return False


def recover(
    name: str, domains: list[str], timeout: float = 30
) -> list[tuple[str, str | None, bool]]:
    """Probe `name.<domain>` candidates for an archived and/or live host.

    The dependency-free counterpart to a web search when you remember a site's
    name but not its exact host. The shared polite layer rate-limits the probe
    burst.

    Returns:
        (host, latest_capture_timestamp, is_live) for each hit.
    """
    results = []
    for domain in domains:
        host = f"{name}.{domain}"
        latest = host_latest_capture(host, timeout)
        live = host_is_live(host)
        if latest or live:
            results.append((host, latest, live))
    return results


def save_page_now(url: str, timeout: float = 120) -> str | None:
    """Trigger a Wayback 'Save Page Now' capture of a live URL.

    NOTE: this publishes a public snapshot.

    Returns:
        The new archive permalink, or None when the API returned no snapshot.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    resp = polite_get(SAVE_API + url, timeout=timeout)
    loc = resp.headers.get("Content-Location")
    if loc:
        return "https://web.archive.org" + loc
    return resp.url if "/web/" in resp.url else None
