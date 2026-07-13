"""
Platform adapters: each subclass of PlatformAdapter knows how to detect its
platform, find metadata, locate the article body, and clean it. Adding a new
platform/theme means one adapter module plus one entry here; auto-detection and
the --platform flag pick it up automatically.
"""

from bs4 import BeautifulSoup

from .base import PlatformAdapter, Selector
from .docx import DocxAdapter
from .generic import GenericAdapter
from .ghost import GhostAdapter
from .proboards import ProBoardsAdapter
from .wordpress import WordPressAdapter

__all__ = [
    "PLATFORMS",
    "PLATFORM_ALIASES",
    "PlatformAdapter",
    "Selector",
    "detect_platform",
]

# Registry order matters: detect_platform() returns the first match, and
# generic (always-False detect) must never shadow a real platform.
PLATFORMS: dict[str, PlatformAdapter] = {
    adapter.name: adapter
    for adapter in (
        GhostAdapter(),
        WordPressAdapter(),
        ProBoardsAdapter(),
        DocxAdapter(),
        GenericAdapter(),
    )
}

# Friendly aliases accepted on the command line.
PLATFORM_ALIASES = {
    "gh": "ghost",
    "wp": "wordpress",
    "yaaburnee": "wordpress",
    "html": "generic",
    "doc": "docx",
    "word": "docx",
    "pb": "proboards",
    "forum": "proboards",
}


def detect_platform(soup: BeautifulSoup) -> str | None:
    """Sniff the source platform from the page markup.

    Returns:
        A PLATFORMS key, or None if no adapter recognizes the page (the caller
        should ask for --platform).
    """
    for name, adapter in PLATFORMS.items():
        if adapter.detect(soup):
            return name
    return None
