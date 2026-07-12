"""Shared body-cleanup passes used by the platform adapters."""

import re

from bs4 import Tag
from bs4.element import AttributeValueList


def clean_ghost_classes(soup: Tag) -> Tag:
    """Strip Ghost/Koenig CSS classes and data attributes from all tags."""
    for tag in soup.find_all(True):
        classes = tag.get("class")
        if isinstance(classes, list):
            kept = [c for c in classes if not c.startswith(("gh-", "kg-"))]
            if kept:
                tag["class"] = AttributeValueList(kept)
            else:
                del tag["class"]
        for attr in ("data-ghost", "data-kg"):
            if tag.has_attr(attr):
                del tag[attr]
    return soup


def normalize_headings(soup: Tag) -> Tag:
    """Demote any h1 tags after the first to h2.

    Ghost posts often have a second h1 inside the article body.
    """
    h1s = soup.find_all("h1")
    if len(h1s) > 1:
        for h in h1s[1:]:
            h.name = "h2"
    return soup


def clean_wordpress_cruft(soup: Tag) -> Tag:
    """Strip WordPress chrome that adds no editorial value.

    Share bars, related-post blocks, comment threads, and leftover
    scripts/styles. Covers the yaaburnee theme (Kiwi share bars,
    related-article blocks) plus the share/related plugins common across
    generic WP themes (Jetpack/Sharedaddy, jp-relatedposts). Harmless on
    content that has none of these.
    """
    # Exact theme/plugin block classes to drop wholesale.
    for selector in (
        "kiwi-article-bar",
        "related-articles",
        "related-articles-group",
        "related-articles-title",
        "related-post",
        "sharedaddy",
        "jp-relatedposts",
        "sd-sharing",
        "post-navigation",
        "nav-links",
        "comments-area",
        "comment-respond",
        "entry-footer",
    ):
        for el in soup.find_all(class_=selector):
            el.decompose()
    # Plugin widget families matched by class prefix (Kiwi share, Jetpack sharing).
    for el in soup.find_all(class_=re.compile(r"\b(kiwi-|sd-|jp-|sharedaddy)")):
        el.decompose()
    for el in soup.find_all(["script", "style", "noscript", "ins"]):
        el.decompose()
    return soup


def remove_wayback_toolbar(soup: Tag) -> Tag:
    """Strip the Wayback Machine toolbar injected at the top of archived pages."""
    for el in soup.find_all(id=re.compile(r"^wm-")):
        el.decompose()
    for el in soup.find_all("div", class_=re.compile(r"wb_")):
        el.decompose()
    return soup
