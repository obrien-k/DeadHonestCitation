"""The unified `dhc` command-line interface."""

import typer

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
