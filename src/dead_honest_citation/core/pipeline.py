"""
The per-source conversion pipeline: load → detect platform → extract metadata →
locate/clean the body → localize images → embeds/footnotes → Markdown → emit via
the active output target. Plus the Markdown/plain-text passthrough lane.
"""

import os
import re

from bs4 import BeautifulSoup
from markdownify import markdownify as md
from slugify import slugify

from ..adapters import PLATFORMS, detect_platform
from ..adapters.proboards import proboards_collect, proboards_render
from ..config import OUTPUT_DIR
from ..network.polite import polite_get
from ..network.screenshot import screenshot_page
from ..network.wayback import unwrap_wayback, wayback_raw
from ..targets import emit_source, resolve_target
from ..transform.cleanup import remove_wayback_toolbar
from ..transform.embeds import convert_embeds
from ..transform.encoding import fix_cp1252_controls
from ..transform.footnotes import convert_footnotes
from ..transform.frontmatter import first_markdown_heading, parse_simple_front_matter
from ..transform.images import download_cover, download_images
from .capture import capture_binary, is_markup
from .runlog import outcome
from .sources import is_local_source, load_source


def process_url(url, platform=None, target=None, screenshot=False, full_thread=False):
    """Convert one source — a Wayback/live URL or a local HTML file. If platform is
    None, auto-detect it from the markup. target selects the output format/layout
    (defaults to jekyll). Non-HTML URLs are captured verbatim. screenshot renders the
    page to an asset (citation targets only; needs playwright)."""
    tgt = resolve_target(target)
    print(f"\n→ {url}")
    if is_local_source(url):
        try:
            html, base_dir = load_source(url)
        except Exception as e:
            print(f"  ✗ Failed to load: {e}")
            return outcome("failed", reason=f"load: {e}")
    else:
        try:
            resp = polite_get(url)
        except Exception as e:
            print(f"  ✗ Failed to load: {e}")
            return outcome("failed", reason=f"load: {e}")
        base_dir = None
        content_type = resp.headers.get("Content-Type", "")
        if not is_markup(content_type):
            return capture_binary(resp.content, content_type, url, tgt)
        html = resp.text

    html = fix_cp1252_controls(html)
    soup = BeautifulSoup(html, "html.parser")
    soup = remove_wayback_toolbar(soup)

    resolved = platform or detect_platform(soup)
    if resolved is None:
        print("  ✗ Could not detect platform — re-run with --platform; skipping.")
        return outcome("failed", reason="platform not detected")
    if not platform:
        print(f"  · detected platform: {resolved}")
    adapter = PLATFORMS[resolved]

    # Extract metadata before unwrapping so cover img src retains its Wayback timestamp
    title, date, description, tags, cover, categories = adapter["extract_metadata"](soup)

    for a in soup.find_all("a", href=True):
        a["href"] = unwrap_wayback(a["href"])
    # Note: image src is left as the Wayback URL so download_images() can fetch the
    # archived copy (the original domain may be dead); it rewrites src on success.

    # Locate the article body using the platform's content selector(s), trying each
    # in order, then falling back to a generic <article>/<main> if none matched. The
    # selector may be a single (name, attrs) tuple or a list of them.
    selectors = adapter["content"]
    if isinstance(selectors, tuple):
        selectors = [selectors]
    article = None
    for name, attrs in selectors:
        article = soup.find(name, attrs)
        if article:
            break
    article = article or soup.find("article") or soup.find("main")
    if not article:
        print("  ✗ No article content found — skipping.")
        return outcome("skipped", reason="no article content")

    # Forum sources use the original-post model: keep the OP only unless --full-thread,
    # which also crawls a live thread's later pages (proboards_collect needs the URL, so
    # it's done here rather than in the registry's clean()).
    if resolved == "proboards":
        article = proboards_render(proboards_collect(article, url, base_dir, full_thread))
    else:
        article = adapter["clean"](article)

    # When the platform supplied no description, derive one from the first paragraph
    if not description:
        first_p = article.find("p")
        if first_p:
            # separator=" " keeps words apart where inline tags (links) sit between them
            text = first_p.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)  # collapse runs of whitespace
            text = re.sub(r"\s+([,.;:!?])", r"\1", text)  # no space before punctuation
            if len(text) > 160:
                text = text[:160].rsplit(" ", 1)[0] + "…"
            description = text

    slug = slugify(title)
    # The cover is a post field; citation targets get imagery from the screenshot step.
    local_cover = "" if tgt.get("emit") else download_cover(cover, slug, tgt)
    doc_relpath = tgt["doc_relpath"](slug, str(date) if date else None)
    filepath = os.path.join(OUTPUT_DIR, doc_relpath)

    if os.path.exists(filepath):
        print(f"  ↷ Already exists, skipping: {doc_relpath}")
        return outcome("skipped", doc_relpath, reason="exists")

    article = download_images(article, slug, base_dir, tgt)
    article, embed_notes = convert_embeds(article, base_dir)
    article, md_footnotes = convert_footnotes(article)

    markdown = md(str(article), heading_style="ATX", bullets="-")
    markdown = tgt["flavor"](markdown)
    # A page with no body (e.g. a homepage/landing template) is not a post — skip it
    # rather than write an empty file. Embed-only posts still pass: convert_embeds()
    # leaves a Markdown link in the body.
    if not markdown.strip():
        print("  ✗ No meaningful content — skipping.")
        return outcome("skipped", reason="empty body")

    meta = {
        "title": title,
        "date": date,
        "description": description,
        "tags": tags,
        "cover": local_cover,
        "categories": categories,
    }

    # A forum source gets a banner→first-post capture: the visual context of the original
    # post. It's the post's cover image and doubles as citation evidence (described in the
    # citation note). Automatic for the forum model, best-effort (needs playwright); the
    # 'if_' raw capture keeps the Wayback toolbar out of frame.
    if resolved == "proboards":
        shot_dir = os.path.join(OUTPUT_DIR, tgt["asset_dir"](slug))
        os.makedirs(shot_dir, exist_ok=True)
        shot_name = f"{slug}-cover.png"
        first_post = 'td[width="80%"].windowbg, td[width="80%"].windowbg2'
        if screenshot_page(
            wayback_raw(url), os.path.join(shot_dir, shot_name), end_selector=first_post
        ):
            shot_url = tgt["asset_url"](slug, shot_name)
            meta["cover"] = shot_url
            meta["screenshot"] = shot_url
            meta["screenshot_note"] = "Banner-to-first-post capture of the original forum thread."
    # Other sources: an optional full-page evidence shot for citation targets.
    elif screenshot and tgt.get("emit"):
        shot_dir = os.path.join(OUTPUT_DIR, tgt["asset_dir"](slug))
        os.makedirs(shot_dir, exist_ok=True)
        shot_name = f"{slug}-screenshot.png"
        if screenshot_page(url, os.path.join(shot_dir, shot_name)):
            meta["screenshot"] = tgt["asset_url"](slug, shot_name)

    written = emit_source(
        tgt, doc_relpath, url, base_dir, resolved, slug, meta, markdown, md_footnotes
    )
    print(f"  ✓ Saved: {written}")
    for note in embed_notes:
        print(f"  ⚠ NEEDS REVIEW: {note}")
    return outcome("converted", written, reason="; ".join(embed_notes) or None)


def process_markdown(path, target=None):
    """Bring a loose Markdown/plain-text file in as a post/citation, verbatim (no HTML
    round-trip). Title from front matter, first heading, or filename; provenance local."""
    tgt = resolve_target(target)
    print(f"\n→ {path}")
    expanded = os.path.expanduser(path)
    try:
        with open(expanded, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        print(f"  ✗ Failed to load: {e}")
        return outcome("failed", reason=f"load: {e}")
    meta_in, body = parse_simple_front_matter(text)
    body = body.strip("\n")
    if not body.strip():
        print("  ✗ Empty file — skipping.")
        return outcome("skipped", reason="empty file")
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
    meta = {
        "title": title,
        "date": meta_in.get("date", ""),
        "description": description,
        "tags": meta_in.get("tags", []),
        "cover": "",
        "categories": [],
    }
    doc_relpath = tgt["doc_relpath"](slug, meta["date"] or None)
    if os.path.exists(os.path.join(OUTPUT_DIR, doc_relpath)):
        print(f"  ↷ Already exists, skipping: {doc_relpath}")
        return outcome("skipped", doc_relpath, reason="exists")
    written = emit_source(
        tgt, doc_relpath, path, os.path.dirname(expanded), "txt", slug, meta, body + "\n", ""
    )
    print(f"  ✓ Saved: {written}")
    return outcome("converted", written)
