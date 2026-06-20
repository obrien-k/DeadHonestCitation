#!/usr/bin/env python3
"""
Discover archived pages for a domain on the Wayback Machine, so you don't have to
know the URLs up front. Queries the Wayback CDX Server API for every capture of a
domain, optionally filters by a substring of the URL, and prints one Wayback URL
per line — exactly the source format index.py consumes:

    python discover.py example.com                       # every archived HTML page
    python discover.py example.com --contains dish       # only URLs containing "dish"
    python discover.py example.com -o urls.txt           # write a source list
    python discover.py example.com --contains dish | python index.py /dev/stdin

Note on title matching: CDX exposes the captured URL, timestamp, status and
mimetype — *not* the page <title>. So --contains filters on the URL (i.e. the
slug). For Ghost/WordPress the slug is usually derived from the title, so a title
word is normally present in the slug; if it isn't, fetch-and-grep the candidates
instead (out of scope here — keep discovery cheap and offline-of-the-body).
"""

import argparse
import sys

import requests

CDX_API = "https://web.archive.org/cdx/search/cdx"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; archive-2-md/1.0)"}


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


def main():
    p = argparse.ArgumentParser(
        description="List Wayback Machine captures for a domain as index.py sources."
    )
    p.add_argument("domain", help="Domain to enumerate, e.g. example.com (no scheme).")
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
