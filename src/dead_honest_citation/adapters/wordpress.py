"""WordPress adapter, generalized across themes (yaaburnee and later/generic ones)."""

import datetime as dt
import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag
from dateutil import parser as dateparser
from slugify import slugify

from ..models import PostMetadata
from ..transform.cleanup import clean_ghost_classes, clean_wordpress_cruft, normalize_headings
from .base import PlatformAdapter, Selector, as_tag, attr_str, class_list

# Organizational-only categories that add no editorial value.
CATEGORY_NOISE = {"uncategorized", "in-response"}


class WordPressAdapter(PlatformAdapter):
    """WordPress exports, resilient to theme differences in markup."""

    name: ClassVar[str] = "wordpress"
    # WP themes disagree on the body wrapper — try the common ones in order.
    # yaaburnee uses .post-content; later/generic themes use .entry-content;
    # td-/article-content cover a few more. The pipeline falls back to <article>.
    content: ClassVar[Selector | list[Selector]] = [
        ("div", {"class": "post-content"}),
        ("div", {"class": "entry-content"}),
        ("div", {"class": "td-post-content"}),
        ("div", {"class": "article-content"}),
    ]

    def detect(self, soup: BeautifulSoup) -> bool:
        """True if the page looks like a WordPress export (any common theme)."""
        if soup.find("div", class_=re.compile(r"\b(post-content|entry-content)\b")) and soup.find(
            class_=re.compile(r"\b(entry-meta|entry-header|posted-on)\b")
        ):
            return True
        gen = as_tag(soup.find("meta", attrs={"name": "generator"}))
        if "wordpress" in attr_str(gen, "content").lower():
            return True
        # wp-content asset paths are a strong WordPress signal
        return bool(
            soup.find(href=re.compile(r"/wp-content/"))
            or soup.find(src=re.compile(r"/wp-content/"))
        )

    def extract_metadata(self, soup: BeautifulSoup) -> PostMetadata:
        """WordPress metadata, generalized across themes.

        Title, date, tags, and categories each resolve from the first source
        that works, so the adapter is not tied to one theme: title from
        .entry-title → og:title → h1; date from <meta article:published_time> →
        <time datetime> → .post-date/.entry-date text; tags from the yaaburnee
        tag-* classes on <article>; categories from the .entry-meta
        post-category badge. Description is left empty (WP themes rarely emit a
        per-post one) and derived from the first body paragraph in the pipeline.
        """
        # Title: .entry-title → og:title → first h1
        title = ""
        entry_title = soup.find(class_="entry-title")
        if entry_title:
            title = entry_title.get_text(strip=True)
        if not title:
            title = attr_str(as_tag(soup.find("meta", property="og:title")), "content").strip()
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "Untitled"

        # Date: resolve from the first source that parses. Themes disagree on where
        # the publish date lives — yaaburnee uses .post-date (human format,
        # "March 08, 2018"), later/generic WP themes expose
        # <meta article:published_time> or <time datetime>.
        date = _first_parsable_date(soup)

        # Tags: tag-* classes on the <article> wrapper
        article_el = as_tag(soup.find("article"))
        tags = [c[len("tag-") :] for c in class_list(article_el) if c.startswith("tag-")]

        # Categories: the main post's category badge lives in
        # <div class="entry-meta"><span class="post-category"> — the standalone
        # <div class="post-category"> blocks belong to related-article cards.
        categories: list[str] = []
        entry_meta = as_tag(soup.find("div", class_="entry-meta"))
        cat_block = as_tag(entry_meta.find("span", class_="post-category")) if entry_meta else None
        if cat_block:
            categories = [
                a.get_text(strip=True)
                for a in cat_block.find_all("a")
                if a.get_text(strip=True) and slugify(a.get_text(strip=True)) not in CATEGORY_NOISE
            ]

        # The theme has no per-post cover; body images are kept inline instead.
        return PostMetadata(title=title, date=date, tags=tags, categories=categories)

    def clean(self, article: Tag) -> Tag:
        """Cleaning pipeline for yaaburnee WordPress article bodies."""
        article = clean_wordpress_cruft(article)
        article = clean_ghost_classes(article)  # harmless; drops any stray gh-/kg- classes
        article = normalize_headings(article)
        return article


def _first_parsable_date(soup: BeautifulSoup, name_meta_fallback: bool = True) -> dt.date | None:
    """The first date candidate that parses, in trust order.

    Canonical first (unambiguous), then the theme's explicit post-date element,
    and only then a bare <time> — which can belong to a sidebar/recent-posts
    widget or a comment, so it must lose to the post-date class when both exist.
    name_meta_fallback also accepts <meta name="published_time"> (WordPress);
    the generic adapter reads only the property= form.
    """
    candidates: list[str] = []
    meta_pub = as_tag(soup.find("meta", property="article:published_time"))
    if meta_pub is None and name_meta_fallback:
        meta_pub = as_tag(soup.find("meta", {"name": "published_time"}))
    if attr_str(meta_pub, "content"):
        candidates.append(attr_str(meta_pub, "content"))
    for cls in ("post-date", "entry-date", "published", "posted-on"):
        el = as_tag(soup.find(class_=cls))
        if el:
            candidates.append(attr_str(el, "datetime") or el.get_text(" ", strip=True))
    time_el = as_tag(soup.find("time", attrs={"datetime": True}))
    if time_el:
        candidates.append(attr_str(time_el, "datetime"))
    for cand in candidates:
        try:
            return dateparser.parse(cand).date()
        except Exception:
            continue
    return None
