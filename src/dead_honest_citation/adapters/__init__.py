"""
Platform adapters: each registers how to detect the platform, find metadata,
locate the article body, and clean it. Adding a new platform/theme means adding
one entry here (and an extract/clean/detect module); auto-detection and the
--platform flag pick it up automatically.
"""

import re

from .docx import clean_content_docx, detect_docx
from .generic import clean_content_generic, extract_metadata_generic
from .ghost import clean_content_ghost, detect_ghost, extract_metadata_ghost
from .proboards import clean_content_proboards, detect_proboards, extract_metadata_proboards
from .wordpress import clean_content_wordpress, detect_wordpress, extract_metadata_wordpress

PLATFORMS = {
    "ghost": {
        "detect": detect_ghost,
        "extract_metadata": extract_metadata_ghost,
        "content": ("section", {"class": re.compile("gh-content")}),
        "clean": clean_content_ghost,
    },
    "wordpress": {
        "detect": detect_wordpress,
        "extract_metadata": extract_metadata_wordpress,
        # WP themes disagree on the body wrapper — try the common ones in order.
        # yaaburnee uses .post-content; later/generic themes use .entry-content;
        # td-/article-content cover a few more. The pipeline falls back to <article>.
        "content": [
            ("div", {"class": "post-content"}),
            ("div", {"class": "entry-content"}),
            ("div", {"class": "td-post-content"}),
            ("div", {"class": "article-content"}),
        ],
        "clean": clean_content_wordpress,
    },
    # Forum threads (ProBoards/YaBB-lineage). No <article>/<main>; the whole <body>
    # is handed to clean_content_proboards, which rebuilds the thread into attributed
    # author/date blocks. Detection is structural (windowbg cells + viewprofile links).
    "proboards": {
        "detect": detect_proboards,
        "extract_metadata": extract_metadata_proboards,
        "content": ("body", {}),
        "clean": clean_content_proboards,
    },
    # Word documents. docx_to_html() converts the .docx to HTML up front and tags it
    # with a marker meta, so detection is exact; metadata comes from the Word core
    # properties we inject as og/meta tags (extract_metadata_generic reads them).
    "docx": {
        "detect": detect_docx,
        "extract_metadata": extract_metadata_generic,
        "content": ("article", {}),
        "clean": clean_content_docx,
    },
    # Last-resort adapter for arbitrary HTML (e.g. a locally saved page from an
    # unknown CMS). Opt-in only — detect() returns False so it never shadows a real
    # platform during auto-detection; select it with --platform generic / --html.
    "generic": {
        "detect": lambda soup: False,
        "extract_metadata": extract_metadata_generic,
        "content": [
            ("div", {"class": "entry-content"}),
            ("div", {"class": "post-content"}),
            ("article", {}),
            ("main", {}),
            ("div", {"class": re.compile(r"\b(post|article|content)\b")}),
        ],
        "clean": clean_content_generic,
    },
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


def detect_platform(soup):
    """
    Sniff the source platform from the page markup. Returns a PLATFORMS key, or
    None if no adapter recognizes the page (caller should ask for --platform).
    """
    for name, adapter in PLATFORMS.items():
        if adapter["detect"](soup):
            return name
    return None
