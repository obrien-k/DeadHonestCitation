"""The platform-adapter contract, plus small typed helpers for BeautifulSoup."""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from bs4 import BeautifulSoup, Tag

from ..models import PostMetadata

# A body-locating selector: (tag_name, attrs) as accepted by soup.find().
Selector = tuple[str, dict[str, Any]]


class PlatformAdapter(ABC):
    """One source CMS/theme/format the converter can read.

    Adding a platform means one subclass (its own module under adapters/) plus a
    registry entry in adapters.PLATFORMS; auto-detection and the --platform flag
    pick it up automatically.

    Attributes:
        name: Registry key, also what --platform accepts.
        content: A selector locating the article body — or a list of them tried
            in order, because themes disagree on the body wrapper. The pipeline
            falls back to <article>/<main> when none match.
        kind: Content kind for the citation record (post / page / thread / …).
        is_thread: True for conversation sources (forums, comment threads). The
            pipeline routes these through render_thread() instead of clean(),
            and applies the original-post model — only the OP is kept unless
            --full-thread.
        thread_shot_selector: CSS selector for the end of a thread's automatic
            banner→first-post screenshot, or None for no automatic capture.
    """

    name: ClassVar[str]
    content: ClassVar[Selector | list[Selector]]
    kind: ClassVar[str] = "post"
    is_thread: ClassVar[bool] = False
    thread_shot_selector: ClassVar[str | None] = None

    @abstractmethod
    def detect(self, soup: BeautifulSoup) -> bool:
        """Recognize this platform from page markup (drives auto-detection)."""

    @abstractmethod
    def extract_metadata(self, soup: BeautifulSoup) -> PostMetadata:
        """Pull title/date/description/tags/cover/categories from the page."""

    @abstractmethod
    def clean(self, article: Tag) -> Tag:
        """Scrub the located body of theme cruft; returns the cleaned body."""

    def render_thread(self, article: Tag, url: str, base_dir: str | None, full_thread: bool) -> Tag:
        """Rebuild a conversation as attributed blocks (is_thread adapters only).

        Takes the URL/base_dir because a live thread may need its later pages
        crawled, which the clean() contract has no way to express.
        """
        raise NotImplementedError(f"{self.name} is not a thread platform")


def as_tag(node: object) -> Tag | None:
    """Narrow a soup.find() result to a Tag (find can also yield a string)."""
    return node if isinstance(node, Tag) else None


def attr_str(tag: Tag | None, attr: str) -> str:
    """A tag attribute's string value, or "" when the tag/attr is missing.

    Multi-valued attributes (bs4 returns those as lists) also yield "" — the
    attributes read through this helper (content, datetime, href, src) are
    single-valued by spec.
    """
    if tag is None:
        return ""
    value = tag.get(attr)
    return value if isinstance(value, str) else ""


def class_list(tag: Tag | None) -> list[str]:
    """A tag's class names, or [] when absent (bs4 types class as multi-valued)."""
    if tag is None:
        return []
    value = tag.get("class")
    return list(value) if isinstance(value, list) else []
