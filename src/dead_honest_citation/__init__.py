"""DeadHonestCitation: archived/live web sources → provenance-stamped Markdown."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Read the installed distribution's version so pyproject.toml stays the single
    # source of truth. Hand-kept copies drift: the polite User-Agent still said 0.3
    # after the v0.4.0 bump, and nothing caught it.
    __version__ = version("dead-honest-citation")
except PackageNotFoundError:  # a source tree that was never pip-installed
    __version__ = "0.0.0+unknown"
