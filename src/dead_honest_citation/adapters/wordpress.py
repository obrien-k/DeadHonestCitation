"""WordPress adapter, generalized across themes (yaaburnee and later/generic ones)."""

import re

from dateutil import parser as dateparser
from slugify import slugify

from ..transform.cleanup import clean_ghost_classes, clean_wordpress_cruft, normalize_headings


def detect_wordpress(soup):
    """True if the page looks like a WordPress export (any common theme)."""
    if soup.find("div", class_=re.compile(r"\b(post-content|entry-content)\b")) and soup.find(
        class_=re.compile(r"\b(entry-meta|entry-header|posted-on)\b")
    ):
        return True
    gen = soup.find("meta", attrs={"name": "generator"})
    if gen and "wordpress" in gen.get("content", "").lower():
        return True
    # wp-content asset paths are a strong WordPress signal
    return bool(
        soup.find(href=re.compile(r"/wp-content/")) or soup.find(src=re.compile(r"/wp-content/"))
    )


def extract_metadata_wordpress(soup):
    """
    WordPress, generalized across themes. Title, date, tags, and categories each
    resolve from the first source that works, so the adapter is not tied to one
    theme: title from .entry-title → og:title → h1; date from
    <meta article:published_time> → <time datetime> → .post-date/.entry-date text;
    tags from the yaaburnee tag-* classes on <article>; categories from the
    .entry-meta post-category badge. Description is left empty (WP themes rarely
    emit a per-post one) and derived from the first body paragraph in the pipeline.
    """
    # Title: .entry-title → og:title → first h1
    title = None
    entry_title = soup.find(class_="entry-title")
    if entry_title:
        title = entry_title.get_text(strip=True)
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else "Untitled"

    # Date: resolve from the first source that parses. Themes disagree on where the
    # publish date lives — yaaburnee uses .post-date (human format, "March 08, 2018"),
    # later/generic WP themes expose <meta article:published_time> or <time datetime>.
    date = None
    date_candidates = []
    # Canonical first (unambiguous), then the theme's explicit post-date element,
    # and only then a bare <time> — which can belong to a sidebar/recent-posts
    # widget or a comment, so it must lose to the post-date class when both exist.
    meta_pub = soup.find("meta", property="article:published_time") or soup.find(
        "meta", {"name": "published_time"}
    )
    if meta_pub and meta_pub.get("content"):
        date_candidates.append(meta_pub["content"])
    for cls in ("post-date", "entry-date", "published", "posted-on"):
        el = soup.find(class_=cls)
        if el:
            date_candidates.append(el.get("datetime") or el.get_text(" ", strip=True))
    time_el = soup.find("time", attrs={"datetime": True})
    if time_el:
        date_candidates.append(time_el["datetime"])
    for cand in date_candidates:
        try:
            date = dateparser.parse(cand).date()
            break
        except Exception:
            continue

    # Tags: tag-* classes on the <article> wrapper
    tags = []
    article_el = soup.find("article")
    if article_el and article_el.has_attr("class"):
        tags = [c[len("tag-") :] for c in article_el["class"] if c.startswith("tag-")]

    # Categories: the main post's category badge lives in
    # <div class="entry-meta"><span class="post-category"> — the standalone
    # <div class="post-category"> blocks belong to related-article cards.
    # Organizational-only categories are dropped.
    CATEGORY_NOISE = {"uncategorized", "in-response"}
    categories = []
    entry_meta = soup.find("div", class_="entry-meta")
    cat_block = entry_meta.find("span", class_="post-category") if entry_meta else None
    if cat_block:
        categories = [
            a.get_text(strip=True)
            for a in cat_block.find_all("a")
            if a.get_text(strip=True) and slugify(a.get_text(strip=True)) not in CATEGORY_NOISE
        ]

    # The theme has no per-post cover; body images are kept inline instead.
    return title, date, "", tags, "", categories


def clean_content_wordpress(article):
    """Cleaning pipeline for yaaburnee WordPress article bodies."""
    article = clean_wordpress_cruft(article)
    article = clean_ghost_classes(article)  # harmless; drops any stray gh-/kg- classes
    article = normalize_headings(article)
    return article
