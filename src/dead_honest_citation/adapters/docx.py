"""Word (.docx) adapter: mammoth conversion up front, Word core properties as metadata."""

import os
import tempfile
import zipfile
from collections.abc import Callable
from typing import Any, ClassVar
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, Tag

from ..models import PostMetadata
from ..transform.cleanup import normalize_headings
from .base import PlatformAdapter, Selector, as_tag, attr_str
from .generic import extract_metadata_generic


def _esc(s: str) -> str:
    """Minimal HTML-attribute escaping for values we inject into the <head>."""
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def read_docx_core_props(path: str) -> tuple[str, str, str]:
    """Pull (title, author, created) from a .docx's docProps/core.xml.

    Each is "" when absent. Word leaves dc:title empty unless the author set
    Document Properties, so the title usually has to come from the first
    heading instead (handled downstream).
    """
    title = author = created = ""
    try:
        with zipfile.ZipFile(path) as z:
            data = z.read("docProps/core.xml")
    except (KeyError, zipfile.BadZipFile, OSError):
        return title, author, created
    ns = {"dc": "http://purl.org/dc/elements/1.1/", "dcterms": "http://purl.org/dc/terms/"}
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return title, author, created

    def txt(tag: str) -> str:
        el = root.find(tag, ns)
        return el.text.strip() if el is not None and el.text else ""

    return txt("dc:title"), txt("dc:creator"), txt("dcterms:created")


def _docx_image_handler(out_dir: str) -> Callable[[Any], dict[str, str]]:
    """mammoth image handler: write each embedded image into out_dir/media/ and
    reference it by a relative path, so download_images() copies it like any
    other local-export asset (no network)."""
    media_dir = os.path.join(out_dir, "media")
    os.makedirs(media_dir, exist_ok=True)
    counter = {"n": 0}

    def handle(image: Any) -> dict[str, str]:
        counter["n"] += 1
        ext = (image.content_type or "image/png").split("/")[-1].lower()
        ext = {"jpeg": "jpg", "x-emf": "emf", "x-wmf": "wmf"}.get(ext, ext)
        rel = f"media/image{counter['n']}.{ext}"
        with image.open() as src, open(os.path.join(out_dir, rel), "wb") as dst:
            dst.write(src.read())
        return {"src": rel}

    return handle


def docx_to_html(path: str) -> tuple[str, str]:
    """Convert a .docx into the shape the pipeline expects from a saved HTML page.

    Produces a full document whose <head> carries the Word core properties as
    meta tags (so the docx adapter reads them like any CMS) and whose <body>
    wraps the converted content in <article>. Embedded images are extracted to
    a temp dir, which is returned as base_dir so download_images() copies them
    locally.

    Args:
        path: Filesystem path of the .docx.

    Returns:
        (html, base_dir) — the wrapped HTML document and the directory image
        srcs are relative to.
    """
    import mammoth  # lazy: only needed for .docx, keeps the dep optional otherwise

    out_dir = tempfile.mkdtemp(prefix="dhc-docx-")
    with open(path, "rb") as f:
        result = mammoth.convert_to_html(
            f, convert_image=mammoth.images.img_element(_docx_image_handler(out_dir))
        )
    body = result.value

    title, author, created = read_docx_core_props(path)
    meta = ['<meta name="generator" content="docx (DeadHonestCitation)">']
    if title:
        meta.append(f'<meta property="og:title" content="{_esc(title)}">')
    if author:
        meta.append(f'<meta name="author" content="{_esc(author)}">')
    if created:
        meta.append(f'<meta property="article:published_time" content="{_esc(created)}">')
    head = "".join(meta)
    html = f"<html><head>{head}</head><body><article>{body}</article></body></html>"
    return html, out_dir


class DocxAdapter(PlatformAdapter):
    """Word documents, pre-converted by docx_to_html() and tagged with a marker
    meta so detection is exact; metadata comes from the Word core properties we
    inject as og/meta tags (the generic extraction reads them)."""

    name: ClassVar[str] = "docx"
    content: ClassVar[Selector | list[Selector]] = ("article", {})

    def detect(self, soup: BeautifulSoup) -> bool:
        """True for the wrapped HTML docx_to_html() produces (marker generator meta)."""
        gen = as_tag(soup.find("meta", attrs={"name": "generator"}))
        return "docx" in attr_str(gen, "content").lower()

    def extract_metadata(self, soup: BeautifulSoup) -> PostMetadata:
        return extract_metadata_generic(soup)

    def clean(self, article: Tag) -> Tag:
        """Cleaning pipeline for Word-converted bodies.

        Drops the leading heading (it becomes the front-matter title, so keeping
        it duplicates the title in the body) and the empty bookmark anchors
        (<a id="_Hlk…"></a>) Word/mammoth leave behind.
        """
        first_heading = article.find(["h1", "h2", "h3"])
        if first_heading:
            first_heading.decompose()
        for a in article.find_all("a"):
            # Empty, hrefless anchors are Word bookmarks — pure noise. Drop them.
            if not a.get("href") and not a.get_text(strip=True) and not a.find("img"):
                a.decompose()
        article = normalize_headings(article)
        return article
