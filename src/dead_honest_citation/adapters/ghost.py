"""Ghost adapter: Open Graph metadata, gh-content body, Koenig class scrub."""

import re

from dateutil import parser as dateparser

from ..transform.cleanup import clean_ghost_classes, normalize_headings


def detect_ghost(soup):
    """True if the page looks like a Ghost export."""
    if soup.find("section", class_=re.compile("gh-content")):
        return True
    gen = soup.find("meta", attrs={"name": "generator"})
    return bool(gen and gen.get("content", "").lower().startswith("ghost"))


def extract_metadata_ghost(soup):
    """
    Ghost: title, date, description, and tags come from Open Graph / meta tags;
    the cover is the first <figure> outside the gh-content body. Categories are
    left empty so the jekyll target derives one from the first tag.
    """
    # Title: OG → first h1
    og_title = soup.find("meta", property="og:title")
    title = og_title["content"].strip() if og_title and og_title.get("content") else None
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else "Untitled"

    # Date
    date_meta = soup.find("meta", property="article:published_time") or soup.find(
        "meta", {"name": "published_time"}
    )
    date = None
    if date_meta and date_meta.get("content"):
        try:
            date = dateparser.parse(date_meta["content"]).date()
        except Exception:
            pass

    # Description: OG → meta description
    og_desc = soup.find("meta", property="og:description")
    desc_meta = soup.find("meta", {"name": "description"})
    description = ""
    if og_desc and og_desc.get("content"):
        description = og_desc["content"].strip()
    elif desc_meta and desc_meta.get("content"):
        description = desc_meta["content"].strip()

    # Tags
    tags = [m["content"] for m in soup.find_all("meta", property="article:tag") if m.get("content")]

    # Cover image: first <figure> outside the article body (Ghost puts the feature
    # image in the article header, never inside gh-content)
    cover = ""
    for figure in soup.find_all("figure"):
        if figure.find_parent("section", class_=re.compile("gh-content")):
            continue
        img = figure.find("img")
        if img and img.get("src"):
            cover = img["src"]
            break

    return title, date, description, tags, cover, []


def clean_content_ghost(article):
    """Cleaning pipeline for Ghost article bodies."""
    article = clean_ghost_classes(article)
    article = normalize_headings(article)
    return article
