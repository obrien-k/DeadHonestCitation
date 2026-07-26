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


# Wayback's playback assets, by URL. The rewrite include pulls bundle-playback.js,
# wombat.js, ruffle, and the banner stylesheets from this host.
_WB_ASSET = re.compile(r"web-static\.archive\.org|/_static/")
# Inline bootstrap the rewrite include emits alongside those assets.
_WB_INLINE = re.compile(r"__wm\.|RufflePlayer|wombat")


def remove_wayback_toolbar(soup: Tag) -> Tag:
    """Strip the Wayback Machine chrome injected into archived pages.

    Two separate things, both archive furniture rather than page content: the
    rendered toolbar (`#wm-*`, `div.wb_*`) and the `<head>` rewrite include that
    loads it. The toolbar only exists once bundle-playback.js has run, so a raw
    fetch usually carries the include alone — stripping just the toolbar would
    leave every archived page's markup salted with archive.org assets.
    """
    for el in soup.find_all(id=re.compile(r"^wm-")):
        el.decompose()
    for el in soup.find_all("div", class_=re.compile(r"wb_")):
        el.decompose()
    for el in soup.find_all(["script", "link"]):
        ref = el.get("src") or el.get("href") or ""
        if isinstance(ref, str) and _WB_ASSET.search(ref):
            el.decompose()
        elif not ref and _WB_INLINE.search(el.get_text()):
            el.decompose()
    return soup
