"""dhc discover — find Wayback captures without knowing the URLs up front."""

import sys
from typing import Annotated

import requests
import typer

from ..network import wayback

discover_app = typer.Typer(no_args_is_help=True)


@discover_app.command()
def domain(
    domain: Annotated[
        str, typer.Argument(help="Domain to enumerate, e.g. example.com (no scheme).")
    ],
    contains: Annotated[
        str,
        typer.Option(
            "--contains",
            "-c",
            help="Keep only URLs whose slug contains this substring (case-insensitive).",
        ),
    ] = None,
    status: Annotated[
        str, typer.Option("--status", help='HTTP status to keep (default "200"; "" for any).')
    ] = "200",
    any_type: Annotated[
        bool, typer.Option("--any-type", help="Don't restrict to text/html captures.")
    ] = False,
    newest: Annotated[
        bool,
        typer.Option("--newest", help="Keep each URL's most recent capture (default: earliest)."),
    ] = False,
    output: Annotated[
        str, typer.Option("--output", "-o", help="Write URLs to this file instead of stdout.")
    ] = None,
):
    """Enumerate a known domain's archived captures (prints convert sources, one per line).

    Note on title matching: CDX exposes the captured URL, timestamp, status and
    mimetype — not the page <title>. So --contains filters on the URL (i.e. the
    slug). For Ghost/WordPress the slug is usually derived from the title, so a
    title word is normally present in the slug."""
    # Strip a scheme if the user pasted one; CDX wants a bare host.
    domain = domain.replace("https://", "").replace("http://", "").strip("/")

    try:
        rows = wayback.discover(
            domain,
            contains=contains,
            status=status or None,
            mimetype=None if any_type else "text/html",
            newest=newest,
        )
    except requests.RequestException as e:
        print(f"✗ CDX query failed: {e}", file=sys.stderr)
        raise typer.Exit(1) from e

    urls = [wayback.wayback_url(ts, orig) for ts, orig in rows]

    note = f" containing '{contains}'" if contains else ""
    print(f"Found {len(urls)} archived URL(s) for {domain}{note}.", file=sys.stderr)

    if not urls:
        raise typer.Exit(0)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write("\n".join(urls) + "\n")
        print(f"→ wrote {len(urls)} URL(s) to {output}", file=sys.stderr)
    else:
        print("\n".join(urls))


@discover_app.command()
def recover(
    name: Annotated[str, typer.Argument(help="Remembered site name to recover a host for.")],
    on: Annotated[
        list[str],
        typer.Option("--on", help="Extra hosting domain(s) to probe (repeatable)."),
    ] = None,
):
    """Recover an unknown host from a remembered name, by probing common hosting
    platforms (and any --on DOMAIN) for an archived and/or live host."""
    domains = list(on) if on else wayback.COMMON_HOSTS
    hits = wayback.recover(name, domains)
    if not hits:
        print(
            f"No archived or live host found for '{name}' on: {', '.join(domains)}",
            file=sys.stderr,
        )
        raise typer.Exit(0)
    print(f"Candidate host(s) for '{name}':", file=sys.stderr)
    for host, latest, live in hits:
        tags = []
        if latest:
            tags.append(f"archived (latest {latest[:8]})")
        if live:
            tags.append("live")
        print(f"  {host}  —  {', '.join(tags)}", file=sys.stderr)
        # Pipeable next step: enumerate the archive if archived, else the live URL.
        print(host if latest else f"https://{host}/")


@discover_app.command()
def save(
    url: Annotated[str, typer.Argument(help="Live URL to archive via Save Page Now.")],
):
    """Save Page Now: archive a live-but-unarchived URL and print its new permalink.
    NOTE: this publishes a public snapshot."""
    try:
        archived = wayback.save_page_now(url)
    except requests.RequestException as e:
        print(f"✗ Save Page Now failed: {e}", file=sys.stderr)
        raise typer.Exit(1) from e
    if not archived:
        print("✗ Save Page Now did not return a snapshot URL.", file=sys.stderr)
        raise typer.Exit(1)
    print(f"✓ Saved → {archived}", file=sys.stderr)
    print(archived)
