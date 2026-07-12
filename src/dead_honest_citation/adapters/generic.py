"""Last-resort adapter for arbitrary HTML pages with no recognized CMS."""

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ..models import PostMetadata
from ..transform.cleanup import clean_ghost_classes, clean_wordpress_cruft, normalize_headings
from .base import PlatformAdapter, Selector, as_tag, attr_str
from .wordpress import _first_parsable_date


def extract_metadata_generic(soup: BeautifulSoup) -> PostMetadata:
    """Best-effort metadata for an arbitrary HTML page with no recognized CMS.

    Reads the conventions almost every theme/SSG emits: Open Graph tags, then
    common title/date/description elements. Tags and categories are left empty.
    Shared with the docx adapter, which plants the same meta tags up front.
    """
    # Title: og:title → .entry-title → h1 → <title>
    title = attr_str(as_tag(soup.find("meta", property="og:title")), "content").strip()
    if not title:
        for el in (soup.find(class_="entry-title"), soup.find("h1"), soup.find("title")):
            if el and el.get_text(strip=True):
                title = el.get_text(strip=True)
                break
    title = title or "Untitled"

    # Date: meta published_time → .post-date/.entry-date → <time datetime>
    date = _first_parsable_date(soup, name_meta_fallback=False)

    # Description: og:description → meta description
    description = ""
    for m in (
        as_tag(soup.find("meta", property="og:description")),
        as_tag(soup.find("meta", {"name": "description"})),
    ):
        if attr_str(m, "content"):
            description = attr_str(m, "content").strip()
            break

    # Cover: og:image
    cover = attr_str(as_tag(soup.find("meta", property="og:image")), "content").strip()

    return PostMetadata(title=title, date=date, description=description, cover=cover)


class GenericAdapter(PlatformAdapter):
    """Opt-in only — detect() is always False so it never shadows a real
    platform during auto-detection; select it with --platform generic / --html."""

    name: ClassVar[str] = "generic"
    content: ClassVar[Selector | list[Selector]] = [
        ("div", {"class": "entry-content"}),
        ("div", {"class": "post-content"}),
        ("article", {}),
        ("main", {}),
        ("div", {"class": re.compile(r"\b(post|article|content)\b")}),
    ]

    def detect(self, soup: BeautifulSoup) -> bool:
        return False

    def extract_metadata(self, soup: BeautifulSoup) -> PostMetadata:
        return extract_metadata_generic(soup)

    def clean(self, article: Tag) -> Tag:
        """Generic body cleanup: drop non-content landmarks, then the shared scrubbers."""
        for el in article.find_all(["nav", "aside", "header", "footer", "form"]):
            el.decompose()
        article = clean_wordpress_cruft(article)  # also covers generic WP share/related plugins
        article = clean_ghost_classes(article)
        article = normalize_headings(article)
        return article
