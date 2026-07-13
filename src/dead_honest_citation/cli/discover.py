"""dhc discover — find Wayback captures without knowing the URLs up front.

Status goes to the stderr console; the discovered URLs/hosts go to stdout via a
plain `print` on purpose — that stream is machine-readable and gets piped into
`dhc convert`, so it must stay free of styling and Rich's width-based wrapping.
"""

from typing import Annotated

import requests
import typer

from ..network import wayback
from ..ui import detail, error, status, success, warn

discover_app = typer.Typer(no_args_is_help=True)


@discover_app.command()
def domain(
    domain: Annotated[
        str, typer.Argument(help="Domain to enumerate, e.g. example.com (no scheme).")
    ],
    contains: Annotated[
        str | None,
        typer.Option(
            "--contains",
            "-c",
            help="Keep only URLs whose slug contains this substring (case-insensitive).",
        ),
    ] = None,
    status_filter: Annotated[
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
        str | None,
        typer.Option("--output", "-o", help="Write URLs to this file instead of stdout."),
    ] = None,
) -> None:
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
            status=status_filter or None,
            mimetype=None if any_type else "text/html",
            newest=newest,
        )
    except requests.RequestException as e:
        error(f"✗ CDX query failed: {e}", err=True)
        raise typer.Exit(1) from e

    urls = [wayback.wayback_url(ts, orig) for ts, orig in rows]

    note = f" containing '{contains}'" if contains else ""
    status(f"Found {len(urls)} archived URL(s) for {domain}{note}.", err=True)

    if not urls:
        raise typer.Exit(0)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write("\n".join(urls) + "\n")
        status(f"→ wrote {len(urls)} URL(s) to {output}", err=True)
    else:
        print("\n".join(urls))


@discover_app.command()
def recover(
    name: Annotated[str, typer.Argument(help="Remembered site name to recover a host for.")],
    on: Annotated[
        list[str] | None,
        typer.Option("--on", help="Extra hosting domain(s) to probe (repeatable)."),
    ] = None,
) -> None:
    """Recover an unknown host from a remembered name, by probing common hosting
    platforms (and any --on DOMAIN) for an archived and/or live host."""
    domains = list(on) if on else wayback.COMMON_HOSTS
    hits = wayback.recover(name, domains)
    if not hits:
        warn(
            f"No archived or live host found for '{name}' on: {', '.join(domains)}",
            err=True,
        )
        raise typer.Exit(0)
    status(f"Candidate host(s) for '{name}':", err=True)
    for host, latest, live in hits:
        tags = []
        if latest:
            tags.append(f"archived (latest {latest[:8]})")
        if live:
            tags.append("live")
        detail(f"  {host}  —  {', '.join(tags)}", err=True)
        # Pipeable next step: enumerate the archive if archived, else the live URL.
        print(host if latest else f"https://{host}/")


@discover_app.command()
def save(
    url: Annotated[str, typer.Argument(help="Live URL to archive via Save Page Now.")],
) -> None:
    """Save Page Now: archive a live-but-unarchived URL and print its new permalink.
    NOTE: this publishes a public snapshot."""
    try:
        archived = wayback.save_page_now(url)
    except requests.RequestException as e:
        error(f"✗ Save Page Now failed: {e}", err=True)
        raise typer.Exit(1) from e
    if not archived:
        error("✗ Save Page Now did not return a snapshot URL.", err=True)
        raise typer.Exit(1)
    success(f"✓ Saved → {archived}", err=True)
    print(archived)
