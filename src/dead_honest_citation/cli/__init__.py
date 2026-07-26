"""The unified `dhc` command-line interface."""

from typing import Annotated

import typer

from .. import __version__
from ..ui import console, setup_logging
from .convert import clean, convert, prune
from .discover import discover_app
from .stage import menu, promote, stage
from .wizard import wizard

app = typer.Typer(
    help="DeadHonestCitation: turn archived and locally-saved web sources into "
    "provenance-stamped, citable Markdown.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(show: bool) -> None:
    """Print the version and exit — eager, so `dhc --version` needs no subcommand."""
    if show:
        console.print(f"dhc {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Verbose logging (per-request HTTP tracing)."),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show the installed version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Configure logging before any subcommand runs."""
    setup_logging(verbose)


app.command()(convert)
app.add_typer(
    discover_app,
    name="discover",
    help="Find Wayback captures: enumerate a domain, recover a host by name, "
    "or Save Page Now a live URL.",
)
app.command()(stage)
app.command()(promote)
app.command()(menu)
app.command()(wizard)
app.command()(clean)
app.command()(prune)


def main() -> None:
    app()
