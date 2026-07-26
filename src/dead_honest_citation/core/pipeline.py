"""
The per-source conversion pipeline: load → detect platform → extract metadata →
locate/clean the body → localize images → embeds/footnotes → Markdown → emit via
the active output target. Plus the Markdown/plain-text passthrough lane.

`process_url` / `process_markdown` are the orchestration boundary: the inner
`_convert_*` helpers raise the package exceptions at their failure sites, and the
boundary turns each into an `Outcome` so a batch never dies on one source and the
run log gets an actionable reason.
"""

import datetime as dt
import os
import re

import requests
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md
from slugify import slugify

from ..adapters import PLATFORMS, detect_platform
from ..adapters.proboards import proboards_collect, proboards_render
from ..config import OUTPUT_DIR
from ..exceptions import ContentNotFoundError, DHCError, EmitError, FetchError, PlatformDetectError
from ..models import Outcome, PostMetadata
from ..network.polite import polite_get
from ..network.screenshot import screenshot_page
from ..network.wayback import unwrap_wayback, wayback_raw
from ..targets import resolve_target
from ..transform.cleanup import remove_wayback_toolbar
from ..transform.embeds import convert_embeds
from ..transform.encoding import fix_cp1252_controls
from ..transform.footnotes import convert_footnotes
from ..transform.frontmatter import first_markdown_heading, parse_simple_front_matter
from ..transform.images import download_cover, download_images
from ..ui import detail, error, status, success, warn
from .capture import capture_binary, capture_page, is_markup
from .sources import is_local_source, load_source


def process_url(
    url: str,
    platform: str | None = None,
    target: str | None = None,
    screenshot: bool = False,
    full_thread: bool = False,
) -> Outcome:
    """Convert one source — a Wayback/live URL or a local HTML file.

    Non-HTML URLs are captured verbatim instead of converted. The orchestration
    boundary: catches the package exceptions the inner conversion raises and maps
    them to a terminal Outcome so callers (the batch loop, the wizard) never see
    an exception escape.

    Args:
        url: A Wayback/live URL or a local .html/.htm/.docx path.
        platform: A PLATFORMS key to force; None auto-detects from the markup.
        target: Output format/layout name or alias (defaults to jekyll).
        screenshot: Render the page to a PNG referenced from its citation
            (citation targets only; needs playwright).
        full_thread: Forum sources — keep every post instead of just the OP.

    Returns:
        The source's terminal Outcome (converted / captured / skipped / failed).
    """
    status(f"\n→ {url}")
    try:
        return _convert_url(url, platform, target, screenshot, full_thread)
    except FetchError as e:
        error(f"  ✗ Failed to load: {e}")
        return Outcome("failed", reason=f"load: {e}")
    except PlatformDetectError as e:
        error(f"  ✗ {e}; skipping.")
        return Outcome("failed", reason="platform not detected")
    except ContentNotFoundError as e:
        error(f"  ✗ {e} — skipping.")
        return Outcome("skipped", reason="no article content")
    except EmitError as e:
        error(f"  ✗ Failed to write: {e}")
        return Outcome("failed", reason=f"emit: {e}")


def _convert_url(
    url: str,
    platform: str | None,
    target: str | None,
    screenshot: bool,
    full_thread: bool,
) -> Outcome:
    """The conversion body. Raises DHCError subclasses at failure sites."""
    tgt = resolve_target(target)
    base_dir: str | None
    if is_local_source(url):
        try:
            html, base_dir = load_source(url)
        except Exception as e:
            raise FetchError(str(e)) from e
    else:
        try:
            resp = polite_get(url)
        except FetchError:
            raise  # already typed (e.g. WaybackRateLimitError) — keep it
        except requests.RequestException as e:
            raise FetchError(str(e)) from e
        base_dir = None
        content_type = resp.headers.get("Content-Type", "")
        if not is_markup(content_type):
            return capture_binary(resp.content, content_type, url, tgt)
        html = resp.text

    html = fix_cp1252_controls(html)
    soup = BeautifulSoup(html, "html.parser")
    remove_wayback_toolbar(soup)  # mutates in place

    # Platform cascade. detect_platform() stays strict — it answers "which CMS is
    # this?" and None means none — but an unrecognized page is still a page, so the
    # pipeline falls through to the generic adapter rather than dead-ending. Only an
    # explicit --platform pins the choice; auto never refuses to try.
    if platform is not None and platform not in PLATFORMS:
        known = ", ".join(PLATFORMS)
        raise PlatformDetectError(f"Unknown platform {platform!r} — known platforms: {known}")
    detected = platform or detect_platform(soup)
    resolved = detected or "generic"
    if not platform:
        if detected:
            detail(f"  · detected platform: {resolved}")
        else:
            detail("  · no CMS recognized — reading as generic HTML")
    adapter = PLATFORMS[resolved]

    # Extract metadata before unwrapping so cover img src retains its Wayback timestamp
    meta = adapter.extract_metadata(soup)

    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if isinstance(href, str):
            a["href"] = unwrap_wayback(href)
    # Note: image src is left as the Wayback URL so download_images() can fetch the
    # archived copy (the original domain may be dead); it rewrites src on success.

    # Locate the article body using the platform's content selector(s), trying each
    # in order, then falling back to a generic <article>/<main> if none matched.
    selectors = adapter.content if isinstance(adapter.content, list) else [adapter.content]
    article: Tag | None = None
    for name, attrs in selectors:
        found = soup.find(name, attrs)
        if isinstance(found, Tag):
            article = found
            break
    if article is None:
        fallback = soup.find("article") or soup.find("main")
        article = fallback if isinstance(fallback, Tag) else None
    if article is None:
        if platform is None:
            return capture_page(html, url, tgt, meta)
        raise ContentNotFoundError("No article content found")

    # Forum sources use the original-post model: keep the OP only unless --full-thread,
    # which also crawls a live thread's later pages (proboards_collect needs the URL, so
    # it's done here rather than through the adapter's clean()).
    if resolved == "proboards":
        article = proboards_render(proboards_collect(article, url, base_dir, full_thread))
    else:
        article = adapter.clean(article)

    # When the platform supplied no description, derive one from the first paragraph
    if not meta.description:
        first_p = article.find("p")
        if isinstance(first_p, Tag):
            # separator=" " keeps words apart where inline tags (links) sit between them
            text = first_p.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)  # collapse runs of whitespace
            text = re.sub(r"\s+([,.;:!?])", r"\1", text)  # no space before punctuation
            if len(text) > 160:
                text = text[:160].rsplit(" ", 1)[0] + "…"
            meta.description = text

    slug = slugify(meta.title)
    # The cover is a post field; citation targets get imagery from the screenshot step.
    meta.cover = "" if tgt.is_citation else download_cover(meta.cover, slug, tgt)
    doc_relpath = tgt.doc_relpath(slug, meta.date)
    filepath = os.path.join(OUTPUT_DIR, doc_relpath)

    if os.path.exists(filepath):
        detail(f"  ↷ Already exists, skipping: {doc_relpath}")
        return Outcome("skipped", doc_relpath, reason="exists")

    article = download_images(article, slug, base_dir, tgt)
    article, embed_notes = convert_embeds(article, base_dir)
    article, md_footnotes = convert_footnotes(article)

    markdown = md(str(article), heading_style="ATX", bullets="-")
    markdown = tgt.flavor(markdown)
    # A page with no body (e.g. a homepage/landing template) is not a post — skip it
    # rather than write an empty file. Embed-only posts still pass: convert_embeds()
    # leaves a Markdown link in the body.
    if not markdown.strip():
        if platform is None:
            return capture_page(html, url, tgt, meta)
        error("  ✗ No meaningful content — skipping.")
        return Outcome("skipped", reason="empty body")

    # A forum source gets a banner→first-post capture: the visual context of the original
    # post. It's the post's cover image and doubles as citation evidence (described in the
    # citation note). Automatic for the forum model, best-effort (needs playwright); the
    # 'if_' raw capture keeps the Wayback toolbar out of frame.
    if resolved == "proboards":
        shot_dir = os.path.join(OUTPUT_DIR, tgt.asset_dir(slug))
        os.makedirs(shot_dir, exist_ok=True)
        shot_name = f"{slug}-cover.png"
        first_post = 'td[width="80%"].windowbg, td[width="80%"].windowbg2'
        if screenshot_page(
            wayback_raw(url), os.path.join(shot_dir, shot_name), end_selector=first_post
        ):
            shot_url = tgt.asset_url(slug, shot_name)
            meta.cover = shot_url
            meta.screenshot = shot_url
            meta.screenshot_note = "Banner-to-first-post capture of the original forum thread."
    # Other sources: an optional full-page evidence shot for citation targets.
    elif screenshot and tgt.is_citation:
        shot_dir = os.path.join(OUTPUT_DIR, tgt.asset_dir(slug))
        os.makedirs(shot_dir, exist_ok=True)
        shot_name = f"{slug}-screenshot.png"
        if screenshot_page(url, os.path.join(shot_dir, shot_name)):
            meta.screenshot = tgt.asset_url(slug, shot_name)

    try:
        written = tgt.write(
            doc_relpath, url, base_dir, resolved, slug, meta, markdown, md_footnotes
        )
    except DHCError:
        raise
    except Exception as e:
        raise EmitError(str(e)) from e
    success(f"  ✓ Saved: {written}")
    for note in embed_notes:
        warn(f"  ⚠ NEEDS REVIEW: {note}")
    return Outcome("converted", written, reason="; ".join(embed_notes) or None)


def process_markdown(path: str, target: str | None = None) -> Outcome:
    """Bring a loose Markdown/plain-text file in as a post/citation, verbatim.

    No HTML round-trip: the body is kept as-is; title comes from front matter,
    the first heading, or the filename. Provenance is local.

    Args:
        path: The .md/.markdown (or --txt-mode .txt) file.
        target: Output format/layout name or alias (defaults to jekyll).

    Returns:
        The source's terminal Outcome.
    """
    status(f"\n→ {path}")
    try:
        return _convert_markdown(path, target)
    except FetchError as e:
        error(f"  ✗ Failed to load: {e}")
        return Outcome("failed", reason=f"load: {e}")
    except EmitError as e:
        error(f"  ✗ Failed to write: {e}")
        return Outcome("failed", reason=f"emit: {e}")


def _convert_markdown(path: str, target: str | None) -> Outcome:
    """The Markdown passthrough body. Raises DHCError subclasses at failure sites."""
    tgt = resolve_target(target)
    expanded = os.path.expanduser(path)
    try:
        with open(expanded, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        raise FetchError(str(e)) from e
    meta_in, body = parse_simple_front_matter(text)
    body = body.strip("\n")
    if not body.strip():
        error("  ✗ Empty file — skipping.")
        return Outcome("skipped", reason="empty file")
    stem = os.path.splitext(os.path.basename(expanded))[0]
    title = (
        meta_in.get("title")
        or first_markdown_heading(body)
        or stem.replace("-", " ").replace("_", " ").strip().title()
    )
    description = meta_in.get("description", "")
    if not description:
        plain = re.sub(r"^#{1,6}\s+.*$", "", body, flags=re.M)  # drop heading lines
        plain = re.sub(r"\s+", " ", plain).strip()
        description = plain[:160].rsplit(" ", 1)[0] + "…" if len(plain) > 160 else plain
    slug = slugify(title)
    # Front-matter dates are regex-validated as YYYY-MM-DD by the parser.
    fm_date = meta_in.get("date")
    meta = PostMetadata(
        title=title,
        date=dt.date.fromisoformat(fm_date) if fm_date else None,
        description=description,
        tags=list(meta_in.get("tags", [])),
    )
    doc_relpath = tgt.doc_relpath(slug, meta.date)
    if os.path.exists(os.path.join(OUTPUT_DIR, doc_relpath)):
        detail(f"  ↷ Already exists, skipping: {doc_relpath}")
        return Outcome("skipped", doc_relpath, reason="exists")
    try:
        written = tgt.write(
            doc_relpath, path, os.path.dirname(expanded), "txt", slug, meta, body + "\n", ""
        )
    except DHCError:
        raise
    except Exception as e:
        raise EmitError(str(e)) from e
    success(f"  ✓ Saved: {written}")
    return Outcome("converted", written)
