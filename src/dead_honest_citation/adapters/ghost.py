"""Ghost adapter: Open Graph metadata, gh-content body, Koenig class scrub."""

import datetime as dt
import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag
from dateutil import parser as dateparser

from ..models import PostMetadata
from ..transform.cleanup import clean_ghost_classes, normalize_headings
from .base import PlatformAdapter, Selector, as_tag, attr_str


class GhostAdapter(PlatformAdapter):
    """Ghost exports: metadata from Open Graph / meta tags, body in gh-content."""

    name: ClassVar[str] = "ghost"
    content: ClassVar[Selector | list[Selector]] = (
        "section",
        {"class": re.compile("gh-content")},
    )

    def detect(self, soup: BeautifulSoup) -> bool:
        """True if the page looks like a Ghost export."""
        if soup.find("section", class_=re.compile("gh-content")):
            return True
        gen = as_tag(soup.find("meta", attrs={"name": "generator"}))
        return attr_str(gen, "content").lower().startswith("ghost")

    def extract_metadata(self, soup: BeautifulSoup) -> PostMetadata:
        """Ghost metadata: title, date, description, and tags come from Open
        Graph / meta tags; the cover is the first <figure> outside the
        gh-content body (Ghost puts the feature image in the article header,
        never inside gh-content). Categories are left empty so the jekyll
        target derives one from the first tag."""
        # Title: OG → first h1
        title = attr_str(as_tag(soup.find("meta", property="og:title")), "content").strip()
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "Untitled"

        # Date
        date_meta = as_tag(
            soup.find("meta", property="article:published_time")
            or soup.find("meta", {"name": "published_time"})
        )
        date: dt.date | None = None
        if attr_str(date_meta, "content"):
            try:
                date = dateparser.parse(attr_str(date_meta, "content")).date()
            except Exception:
                pass

        # Description: OG → meta description
        description = ""
        for m in (
            as_tag(soup.find("meta", property="og:description")),
            as_tag(soup.find("meta", {"name": "description"})),
        ):
            if attr_str(m, "content"):
                description = attr_str(m, "content").strip()
                break

        # Tags
        tags = [
            content
            for m in soup.find_all("meta", property="article:tag")
            if (content := attr_str(as_tag(m), "content"))
        ]

        # Cover image: first <figure> outside the article body
        cover = ""
        for figure in soup.find_all("figure"):
            if figure.find_parent("section", class_=re.compile("gh-content")):
                continue
            img = as_tag(figure.find("img"))
            if attr_str(img, "src"):
                cover = attr_str(img, "src")
                break

        return PostMetadata(title=title, date=date, description=description, tags=tags, cover=cover)

    def clean(self, article: Tag) -> Tag:
        """Cleaning pipeline for Ghost article bodies."""
        article = clean_ghost_classes(article)
        article = normalize_headings(article)
        return article
