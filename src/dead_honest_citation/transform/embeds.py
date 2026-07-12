"""Embed handling: keep the personality, drop the ads, surface what needs review."""

import os
import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from ..network.wayback import unwrap_wayback

YOUTUBE_RE = re.compile(r"(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/)([\w-]{6,})")
VIMEO_RE = re.compile(r"vimeo\.com/(?:video/)?(\d+)")
# Embed hosts that are advertising/tracking, not content — dropped without a note.
AD_EMBED_HOSTS = (
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices",
    "amazon-adsystem.com",
    "/ads/",
)


def _anchor(href, text):
    """Build a standalone <a> tag so markdownify renders a proper Markdown link."""
    a = BeautifulSoup("", "html.parser").new_tag("a", href=href)
    a.string = text
    return a


def recover_embed_url(src, base_dir):
    """
    A browser 'Save Page As' rewrites provider iframes (YouTube/Vimeo) to a local
    '<id>.html' file under the page's _files dir. When src points at such a saved
    file, read it and pull the original provider URL back out; otherwise return src.
    """
    if not base_dir or src.startswith(("http://", "https://", "//")):
        return src
    path = os.path.normpath(os.path.join(base_dir, unquote(src.split("?")[0].split("#")[0])))
    if not os.path.isfile(path):
        return src
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return src
    m = re.search(
        r'https?://[^\s"\'<>]*(?:youtube(?:-nocookie)?\.com|youtu\.be|vimeo\.com)[^\s"\'<>]*',
        text,
    )
    return unwrap_wayback(m.group(0)) if m else src


def convert_embeds(article, base_dir=None):
    """
    Replace <iframe>/<embed>/<object> media with Markdown-friendly equivalents so
    it survives the HTML→Markdown step (markdownify drops these tags outright).
    Known providers (YouTube, Vimeo) become labeled links; ad/Flash junk is dropped
    silently. Anything that can't be faithfully represented without a plugin is kept
    as a best-effort link AND recorded as a note for the user to resolve from their
    _drafts/ folder. Returns (article, notes).
    """
    notes = []
    for tag in article.find_all(["iframe", "embed", "object"]):
        src = unwrap_wayback(tag.get("src") or tag.get("data") or "")
        if not src:
            tag.decompose()
            continue
        src = recover_embed_url(src, base_dir)  # un-rewrite browser-localized embeds
        low = src.lower()
        if low.endswith(".swf") or any(h in low for h in AD_EMBED_HOSTS):
            tag.decompose()  # ad/Flash cruft — no personality lost
            continue
        ym, vm = YOUTUBE_RE.search(src), VIMEO_RE.search(src)
        if ym:
            tag.replace_with(
                _anchor(f"https://www.youtube.com/watch?v={ym.group(1)}", "▶ Watch on YouTube")
            )
        elif vm:
            tag.replace_with(_anchor(f"https://vimeo.com/{vm.group(1)}", "▶ Watch on Vimeo"))
        else:
            host = urlparse(src).netloc or src
            tag.replace_with(_anchor(src, f"▶ Embedded content ({host})"))
            notes.append(f"{tag.name} embed kept as a link, not natively convertible: {src}")
    # WordPress shortcodes that need a plugin to render faithfully.
    text = article.get_text(" ", strip=True)
    for sc in sorted(set(re.findall(r"\[(gallery|embed|playlist|audio|video|caption)\b", text))):
        notes.append(f"WordPress [{sc}] shortcode present — needs manual handling")
    return article, notes
