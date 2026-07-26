"""dhc convert / clean / prune — the conversion pipeline and output housekeeping."""

import os
from typing import Annotated

import typer
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from ..adapters import PLATFORM_ALIASES, PLATFORMS
from ..config import RUNLOG
from ..core.housekeeping import clean_output, prune_output
from ..core.pipeline import process_markdown, process_url
from ..core.runlog import log_run
from ..core.sources import collect_sources, is_markdown_source
from ..models import Outcome
from ..targets import TARGET_ALIASES, TARGETS
from ..ui import console, detail, status, warn

_PLATFORM_CHOICES = sorted(set(PLATFORMS) | set(PLATFORM_ALIASES))
_TARGET_CHOICES = sorted(set(TARGETS) | set(TARGET_ALIASES))


def convert(
    sources: Annotated[
        list[str] | None,
        typer.Argument(
            help="One or more sources: a directory (every .html/.htm/.docx inside), a "
            "saved page (.html/.htm), a Word doc (.docx), a Wayback/live URL, or a "
            "list-file of any of those one per line (default: urls.txt)."
        ),
    ] = None,
    recursive: Annotated[
        bool,
        typer.Option(
            "--recursive",
            "-r",
            help="When a source is a directory, recurse into subdirectories "
            "(skips saved-page '<name>_files/' asset folders).",
        ),
    ] = False,
    platform: Annotated[
        str | None,
        typer.Option(
            "--platform",
            "-p",
            help="Force the source platform / theme instead of auto-detecting. "
            f"Accepts: {', '.join(_PLATFORM_CHOICES)}.",
        ),
    ] = None,
    ghost: Annotated[bool, typer.Option("--ghost", help="Shorthand for --platform ghost")] = False,
    wordpress: Annotated[
        bool,
        typer.Option("--wordpress", "--yaaburnee", help="Shorthand for --platform wordpress"),
    ] = False,
    generic: Annotated[
        bool,
        typer.Option(
            "--generic", "--html", help="Shorthand for --platform generic (arbitrary HTML)"
        ),
    ] = False,
    docx: Annotated[
        bool,
        typer.Option("--docx", "--word", help="Shorthand for --platform docx (Word .docx files)"),
    ] = False,
    hackernews: Annotated[
        bool,
        typer.Option(
            "--hacker-news",
            "--hn",
            "-hn",
            help="Shorthand for --platform hackernews (news.ycombinator.com threads)",
        ),
    ] = False,
    txt: Annotated[
        bool,
        typer.Option(
            "--txt",
            "--markdown",
            help="Treat .txt inputs as Markdown/plain-text content (passthrough) instead "
            "of as a list-file of sources. (.md/.markdown are always passthrough.)",
        ),
    ] = False,
    target: Annotated[
        str,
        typer.Option(
            "--target",
            "-t",
            help=f"Output format/layout (default: jekyll). Accepts: {', '.join(_TARGET_CHOICES)}.",
        ),
    ] = "jekyll",
    screenshot: Annotated[
        bool,
        typer.Option(
            "--screenshot",
            help="Render each page to a PNG and reference it from its citation "
            "(--target data; needs playwright).",
        ),
    ] = False,
    note: Annotated[
        str | None,
        typer.Option(
            "--note",
            "-n",
            help="Editorial note recorded on each citation (--target data), rendered "
            "under the provenance line. Use it to say what the archive can't, e.g. "
            "what became of the source since capture.",
        ),
    ] = None,
    full_thread: Annotated[
        bool,
        typer.Option(
            "--full-thread",
            help="Forum sources: keep every post, not just the original. For a live thread "
            "this also crawls the remaining paginated pages (archived/local stay single-page).",
        ),
    ] = False,
) -> None:
    """Convert archived/live web pages, saved HTML, Word docs, or loose Markdown
    into Markdown posts or provenance-stamped citation objects."""
    # Shorthand flags are sugar for --platform; an explicit --platform wins.
    shorthands = (
        (ghost, "ghost"),
        (wordpress, "wordpress"),
        (generic, "generic"),
        (docx, "docx"),
        (hackernews, "hackernews"),
    )
    for flag, name in shorthands:
        if flag and not platform:
            platform = name
    if platform is not None and platform not in _PLATFORM_CHOICES:
        raise typer.BadParameter(
            f"unknown platform {platform!r} (expected one of: {', '.join(_PLATFORM_CHOICES)})"
        )
    if target not in _TARGET_CHOICES:
        raise typer.BadParameter(
            f"unknown target {target!r} (expected one of: {', '.join(_TARGET_CHOICES)})"
        )

    # None ⇒ auto-detect per source from the page markup
    if platform is not None:
        platform = PLATFORM_ALIASES.get(platform, platform)
    resolved_target = TARGET_ALIASES.get(target, target)

    source_list = collect_sources(sources or ["urls.txt"], recursive=recursive, txt_as_content=txt)
    if not source_list:
        warn("No sources to process.")
        raise typer.Exit(0)

    mode = f"as '{platform}'" if platform else "auto-detecting platform"
    status(f"Processing {len(source_list)} source(s), {mode}, → {resolved_target}…")
    tally: dict[str, int] = {}
    # The progress bar shares the ui console, so per-source log lines from the
    # pipeline render above the live bar. Disabled on non-TTY (piped/captured)
    # output so only the log lines remain — no half-rendered bar frames.
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
        disable=not console.is_terminal,
    )
    with progress:
        task = progress.add_task("Converting", total=len(source_list))
        for src in source_list:
            progress.update(
                task, description=f"Converting {os.path.basename(src.rstrip('/')) or src}"
            )
            if is_markdown_source(src, txt):
                result: Outcome = process_markdown(src, resolved_target)
            else:
                result = process_url(
                    src,
                    platform,
                    resolved_target,
                    screenshot=screenshot,
                    full_thread=full_thread,
                    note=note,
                )
            log_run(src, result, resolved_target)
            tally[result.status] = tally.get(result.status, 0) + 1
            progress.advance(task)

    summary = ", ".join(f"{n} {name}" for name, n in sorted(tally.items()))
    status(f"\nDone — {summary or 'nothing processed'}.")
    detail(f"Run log: {RUNLOG}")


def clean(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Delete all generated output (posts + assets)."""
    clean_output(assume_yes=yes)


def prune() -> None:
    """Remove stale output (older slug duplicates, orphaned asset folders)."""
    prune_output()
