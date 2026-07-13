"""
Centralized console + logging so the whole package speaks with one voice.

A single Rich `Console` singleton on stdout carries the semantic status lines
(→ ✓ ✗ ⚠ ↷ ·); the convert progress bar renders on the *same* console, so Rich
interleaves per-source log lines above the live bar rather than fighting it. A
second console on stderr carries logging (and status for commands whose stdout
is machine-readable, e.g. `discover` pipes URLs) — keeping the log stream off
the progress bar's display region.

Styling is applied via the `style=` argument, never inline markup: interpolated
error strings and file paths may contain `[...]` that must not be parsed as
Rich markup. `soft_wrap=True` leaves wrapping to the terminal so a long hint
line stays intact under non-TTY capture.
"""

import logging

from rich.console import Console
from rich.logging import RichHandler

# highlight=False: no automatic recoloring of numbers/paths, so output is
# predictable and colors only mean what we assign.
console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)

log = logging.getLogger("dead_honest_citation")


def _emit(msg: str, style: str | None = None, *, err: bool = False) -> None:
    target = err_console if err else console
    target.print(msg, style=style, markup=False, soft_wrap=True)


def status(msg: str, *, err: bool = False) -> None:
    """A neutral status line (the `→` header, run summaries)."""
    _emit(msg, err=err)


def detail(msg: str, *, err: bool = False) -> None:
    """A secondary/dimmed line (`·` detections, `↷` skips, `↺` prunes)."""
    _emit(msg, "dim", err=err)


def success(msg: str, *, err: bool = False) -> None:
    """A `✓` completion line."""
    _emit(msg, "green", err=err)


def warn(msg: str, *, err: bool = False) -> None:
    """A `⚠`/`⏳` warning (missing image, backoff, NEEDS REVIEW, fallback)."""
    _emit(msg, "yellow", err=err)


def error(msg: str, *, err: bool = False) -> None:
    """A `✗` error line."""
    _emit(msg, "red", err=err)


def setup_logging(verbose: bool = False) -> None:
    """Route the package logger through a RichHandler on stderr.

    Off by default (WARNING); `-v/--verbose` drops it to DEBUG, which surfaces
    the low-level HTTP tracing in `network.polite`. Idempotent — safe to call
    once from the CLI root callback.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=err_console, show_path=False, rich_tracebacks=True)],
    )
    log.setLevel(level)
