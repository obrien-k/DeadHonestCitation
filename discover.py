#!/usr/bin/env python3
"""
Discover archived pages on the Wayback Machine, so you don't have to know the URLs
up front. Three modes:

  # 1. Enumerate a known domain's captures (prints index.py sources, one per line)
  python discover.py example.com
  python discover.py example.com --contains dish       # only URLs containing "dish"
  python discover.py example.com -o urls.txt | python index.py /dev/stdin

  # 2. Recover an unknown host from a remembered *name*, by probing common hosting
  #    platforms (and any --on DOMAIN) for an archived and/or live host
  python discover.py --recover wiistation3
  python discover.py --recover myblog --on example.com

  # 3. Save Page Now: archive a live-but-unarchived URL and print its new permalink
  python discover.py --save https://example.com/page/

Note on title matching: CDX exposes the captured URL, timestamp, status and
mimetype — *not* the page <title>. So --contains filters on the URL (i.e. the
slug). For Ghost/WordPress the slug is usually derived from the title, so a title
word is normally present in the slug; if it isn't, fetch-and-grep the candidates
instead (out of scope here — keep discovery cheap and offline-of-the-body).
"""

import argparse
import sys
import time

import requests

CDX_API = "https://web.archive.org/cdx/search/cdx"
SAVE_API = "https://web.archive.org/save/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; archive-2-md/1.0)"}

# Hosting platforms where a site's name becomes a subdomain — the candidates probed
# by --recover when you remember a name but not the host.
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


def discover(domain, contains=None, status="200", mimetype="text/html", newest=False, timeout=60):
    """Return a list of (timestamp, original_url) for a domain's archived captures.

    One row per unique URL (CDX collapse=urlkey). contains, when set, keeps only
    URLs whose canonical key contains that (lowercased) substring — applied
    server-side as a CDX regex filter. newest swaps the kept capture from the
    earliest to the latest snapshot of each URL."""
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

    resp = requests.get(CDX_API, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()

    rows = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line:
            continue
        timestamp, original = line.split(" ", 1)
        rows.append((timestamp, original))
    return rows


def wayback_url(timestamp, original):
    """Build the playback URL index.py knows how to fetch and de-archive."""
    return f"https://web.archive.org/web/{timestamp}/{original}"


def host_latest_capture(host, timeout=30):
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
        resp = requests.get(CDX_API, params=params, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    line = resp.text.strip()
    return line.split()[0] if line else None


def host_is_live(host, timeout=10):
    """True if the host responds today (tries HTTPS then HTTP)."""
    for scheme in ("https://", "http://"):
        try:
            resp = requests.head(
                scheme + host, headers=HEADERS, timeout=timeout, allow_redirects=True
            )
            if resp.status_code < 400:
                return True
        except requests.RequestException:
            continue
    return False


def recover(name, domains, timeout=30, delay=0.5):
    """Probe `name.<domain>` candidates; return [(host, latest_capture, is_live)] for
    those that are archived and/or live. The dependency-free counterpart to a web
    search when you remember a site's name but not its exact host. A small delay
    between probes keeps the burst polite (the full rate-limit layer lands in step 8)."""
    results = []
    for i, domain in enumerate(domains):
        if i:
            time.sleep(delay)
        host = f"{name}.{domain}"
        latest = host_latest_capture(host, timeout)
        live = host_is_live(host)
        if latest or live:
            results.append((host, latest, live))
    return results


def save_page_now(url, timeout=120):
    """Trigger a Wayback 'Save Page Now' capture of a live URL; return the new
    archive permalink, or None. NOTE: this publishes a public snapshot."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    resp = requests.get(SAVE_API + url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    loc = resp.headers.get("Content-Location")
    if loc:
        return "https://web.archive.org" + loc
    return resp.url if "/web/" in resp.url else None


def _run_recover(args):
    domains = args.on or COMMON_HOSTS
    hits = recover(args.recover, domains)
    if not hits:
        print(
            f"No archived or live host found for '{args.recover}' on: {', '.join(domains)}",
            file=sys.stderr,
        )
        sys.exit(0)
    print(f"Candidate host(s) for '{args.recover}':", file=sys.stderr)
    for host, latest, live in hits:
        tags = []
        if latest:
            tags.append(f"archived (latest {latest[:8]})")
        if live:
            tags.append("live")
        print(f"  {host}  —  {', '.join(tags)}", file=sys.stderr)
        # Pipeable next step: enumerate the archive if archived, else the live URL.
        print(host if latest else f"https://{host}/")


def _run_save(args):
    try:
        archived = save_page_now(args.save)
    except requests.RequestException as e:
        print(f"✗ Save Page Now failed: {e}", file=sys.stderr)
        sys.exit(1)
    if not archived:
        print("✗ Save Page Now did not return a snapshot URL.", file=sys.stderr)
        sys.exit(1)
    print(f"✓ Saved → {archived}", file=sys.stderr)
    print(archived)


def main():
    p = argparse.ArgumentParser(
        description="Discover Wayback captures: enumerate a domain, recover a host by "
        "name, or Save Page Now a live URL."
    )
    p.add_argument("domain", nargs="?", help="Domain to enumerate, e.g. example.com (no scheme).")
    p.add_argument(
        "--recover", metavar="NAME", help="Recover an unknown host from a remembered name."
    )
    p.add_argument(
        "--on",
        action="append",
        metavar="DOMAIN",
        help="Extra hosting domain(s) to probe with --recover (repeatable).",
    )
    p.add_argument(
        "--save", metavar="URL", help="Save Page Now: archive a live URL, print its permalink."
    )
    p.add_argument(
        "--contains",
        "-c",
        default=None,
        help="Keep only URLs whose slug contains this substring (case-insensitive).",
    )
    p.add_argument(
        "--status", default="200", help='HTTP status to keep (default "200"; "" for any).'
    )
    p.add_argument("--any-type", action="store_true", help="Don't restrict to text/html captures.")
    p.add_argument(
        "--newest",
        action="store_true",
        help="Keep each URL's most recent capture (default: earliest).",
    )
    p.add_argument(
        "-o", "--output", default=None, help="Write URLs to this file instead of stdout."
    )
    args = p.parse_args()

    if args.save:
        _run_save(args)
        return
    if args.recover:
        _run_recover(args)
        return
    if not args.domain:
        p.error("give a domain to enumerate, or use --recover NAME / --save URL")

    # Strip a scheme if the user pasted one; CDX wants a bare host.
    domain = args.domain.replace("https://", "").replace("http://", "").strip("/")

    try:
        rows = discover(
            domain,
            contains=args.contains,
            status=args.status or None,
            mimetype=None if args.any_type else "text/html",
            newest=args.newest,
        )
    except requests.RequestException as e:
        print(f"✗ CDX query failed: {e}", file=sys.stderr)
        sys.exit(1)

    urls = [wayback_url(ts, orig) for ts, orig in rows]

    note = f" containing '{args.contains}'" if args.contains else ""
    print(f"Found {len(urls)} archived URL(s) for {domain}{note}.", file=sys.stderr)

    if not urls:
        sys.exit(0)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(urls) + "\n")
        print(f"→ wrote {len(urls)} URL(s) to {args.output}", file=sys.stderr)
    else:
        print("\n".join(urls))


if __name__ == "__main__":
    main()
