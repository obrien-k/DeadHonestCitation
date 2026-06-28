import argparse
import copy
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from markdownify import markdownify as md
from slugify import slugify

from netpolite import polite_get

OUTPUT_DIR = "output"
POSTS_DIR = os.path.join(OUTPUT_DIR, "_posts")
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets", "img", "blog", "posts")
RUNLOG = os.path.join(OUTPUT_DIR, "runlog.jsonl")
# Wayback snapshot URLs carry an optional capture-mode suffix on the timestamp:
# im_ (raw image), if_ (raw iframe), js_, cs_, oe_, etc. Tolerate any of them.
WAYBACK_RE = re.compile(r"(?:https?://web\.archive\.org)?/web/\d+(?:[a-z]{2,3}_)?/(https?://.+)")


def unwrap_wayback(url):
    m = WAYBACK_RE.match(url)
    return m.group(1) if m else url


os.makedirs(POSTS_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# HEADERS / polite_get come from netpolite (shared, rate-limited HTTP layer).


def clean_ghost_classes(soup):
    """Strip Ghost/Koenig CSS classes and data attributes from all tags."""
    for tag in soup.find_all(True):
        if tag.has_attr("class"):
            tag["class"] = [c for c in tag["class"] if not c.startswith(("gh-", "kg-"))]
            if not tag["class"]:
                del tag["class"]
        for attr in ("data-ghost", "data-kg"):
            if tag.has_attr(attr):
                del tag[attr]
    return soup


def normalize_headings(soup):
    """
    Demote any h1 tags after the first to h2.
    Ghost posts often have a second h1 inside the article body.
    """
    h1s = soup.find_all("h1")
    if len(h1s) > 1:
        for h in h1s[1:]:
            h.name = "h2"
    return soup


def clean_wordpress_cruft(soup):
    """
    Strip WordPress chrome that adds no editorial value: share bars, related-post
    blocks, comment threads, and leftover scripts/styles. Covers the yaaburnee
    theme (Kiwi share bars, related-article blocks) plus the share/related plugins
    common across generic WP themes (Jetpack/Sharedaddy, jp-relatedposts). Harmless
    on content that has none of these.
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


def remove_wayback_toolbar(soup):
    """
    Strip the Wayback Machine toolbar injected at the top of archived pages.
    """
    for el in soup.find_all(id=re.compile(r"^wm-")):
        el.decompose()
    for el in soup.find_all("div", class_=re.compile(r"wb_")):
        el.decompose()
    return soup


# ── Images ────────────────────────────────────────────────────────────────────


def wayback_image_candidates(src):
    """
    Given an image src (possibly a Wayback Machine URL), return the ordered list
    of URLs to try when downloading: the archive's raw-image (`im_`) capture
    first, then the bare original. Non-Wayback srcs are returned as-is.
    """
    if src.startswith("/web/"):
        src = "https://web.archive.org" + src
    m = WAYBACK_RE.match(src)
    if not m:
        return [src]
    original = m.group(1)
    ts_match = re.match(r"(?:https?://web\.archive\.org)?/web/(\d+)", src)
    timestamp = ts_match.group(1) if ts_match else ""
    if timestamp:
        return [f"https://web.archive.org/web/{timestamp}im_/{original}", original]
    return [src, original]


def download_image(url, post_img_dir):
    """Download a single image to post_img_dir. Returns the local path, or None on failure."""
    try:
        response = polite_get(url, timeout=15)
        filename = os.path.basename(urlparse(url).path) or "image"
        local_path = os.path.join(post_img_dir, filename)
        with open(local_path, "wb") as f:
            f.write(response.content)
        return local_path
    except Exception as e:
        print(f"  ⚠ Image download failed ({url}): {e}")
        return None


def download_cover(cover_url, slug, target=None):
    """Download the cover image and return its in-document URL, or '' on failure."""
    if not cover_url:
        return ""
    target = target or resolve_target(None)
    post_img_dir = os.path.join(OUTPUT_DIR, target["asset_dir"](slug))
    os.makedirs(post_img_dir, exist_ok=True)

    for url in wayback_image_candidates(cover_url):
        local_path = download_image(url, post_img_dir)
        if local_path:
            return target["asset_url"](slug, os.path.basename(local_path))

    return ""


def download_images(soup, slug, base_dir=None, target=None):
    """
    Download (or, for a local HTML export, copy) all images in the article and
    rewrite their src to the active target's asset URLs. Skips already-localized ones.

    base_dir, when set, is the directory of a saved HTML file; images whose src is
    a relative path are copied straight out of its sibling "<name>_files/" folder
    instead of being fetched over the network.
    """
    target = target or resolve_target(None)
    post_img_dir = os.path.join(OUTPUT_DIR, target["asset_dir"](slug))
    os.makedirs(post_img_dir, exist_ok=True)
    asset_root = target["asset_url"](slug, "")

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src or src.startswith(asset_root):
            continue

        # 1. Local export: copy from the saved files-dir when src resolves on disk.
        if base_dir and not src.startswith(("http://", "https://", "//", "/web/")):
            copied = copy_local_image(src, base_dir, post_img_dir)
            if copied:
                img["src"] = target["asset_url"](slug, os.path.basename(copied))
                continue
            # else fall through: the local file is missing (a cross-origin asset the
            # browser never fetched), so try the real URLs in srcset / data-* below.

        # 2. Download from the best real URL(s) available on the tag — the inline
        # src, then srcset entries (largest first), then common data-* fallbacks.
        localized = False
        for candidate in image_source_urls(img):
            for url in wayback_image_candidates(candidate):
                local_path = download_image(url, post_img_dir)
                if local_path:
                    img["src"] = target["asset_url"](slug, os.path.basename(local_path))
                    localized = True
                    break
            if localized:
                break

        # 3. Nothing worked. Drop a dead local ref so we never emit a broken path;
        # leave a genuine remote src untouched (matches the original behavior).
        if (
            not localized
            and base_dir
            and not src.startswith(("http://", "https://", "//", "/web/"))
        ):
            print(f"  ⚠ Image unrecoverable, dropping: {os.path.basename(src)}")
            img.decompose()

    return soup


def image_source_urls(img):
    """
    Ordered real (http) URLs to try for an <img>: the inline src, then srcset
    candidates (largest width first), then common lazy-load data-* attributes.
    Used as a fallback when a locally saved page's inline src is a dead path — the
    browser typically leaves the original URL behind in srcset.
    """
    urls = []
    src = img.get("src", "")
    if src.startswith(("http://", "https://", "//", "/web/")):
        urls.append(src)
    srcset = img.get("srcset", "")
    if srcset:
        entries = []
        for part in srcset.split(","):
            bits = part.strip().split()
            if bits and bits[0].startswith(("http", "//", "/web/")):
                width = 0
                if len(bits) > 1 and bits[1].endswith("w"):
                    try:
                        width = int(bits[1][:-1])
                    except ValueError:
                        pass
                entries.append((width, bits[0]))
        urls += [u for _, u in sorted(entries, reverse=True)]
    for attr in ("data-orig-file", "data-large-file", "data-src", "data-lazy-src"):
        v = img.get(attr, "")
        if v.startswith(("http", "//", "/web/")):
            urls.append(v)
    seen, ordered = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def copy_local_image(src, base_dir, post_img_dir):
    """Copy an image referenced by a saved HTML page into post_img_dir. Returns the
    destination path, or None if the source file can't be found on disk."""
    rel = unquote(src.split("?")[0].split("#")[0])
    candidate = os.path.normpath(os.path.join(base_dir, rel))
    if not os.path.isfile(candidate):
        return None
    filename = os.path.basename(candidate) or "image"
    dest = os.path.join(post_img_dir, filename)
    try:
        shutil.copyfile(candidate, dest)
        return dest
    except OSError as e:
        print(f"  ⚠ Local image copy failed ({candidate}): {e}")
        return None


# ── Word (.docx) ──────────────────────────────────────────────────────────────


def _esc(s):
    """Minimal HTML-attribute escaping for values we inject into the <head>."""
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def read_docx_core_props(path):
    """
    Pull (title, author, created) from a .docx's docProps/core.xml. Each is "" when
    absent. Word leaves dc:title empty unless the author set Document Properties, so
    the title usually has to come from the first heading instead (handled downstream).
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

    def txt(tag):
        el = root.find(tag, ns)
        return el.text.strip() if el is not None and el.text else ""

    return txt("dc:title"), txt("dc:creator"), txt("dcterms:created")


def _docx_image_handler(out_dir):
    """mammoth image handler: write each embedded image into out_dir/media/ and
    reference it by a relative path, so download_images() copies it like any other
    local-export asset (no network)."""
    media_dir = os.path.join(out_dir, "media")
    os.makedirs(media_dir, exist_ok=True)
    counter = {"n": 0}

    def handle(image):
        counter["n"] += 1
        ext = (image.content_type or "image/png").split("/")[-1].lower()
        ext = {"jpeg": "jpg", "x-emf": "emf", "x-wmf": "wmf"}.get(ext, ext)
        rel = f"media/image{counter['n']}.{ext}"
        with image.open() as src, open(os.path.join(out_dir, rel), "wb") as dst:
            dst.write(src.read())
        return {"src": rel}

    return handle


def docx_to_html(path):
    """
    Convert a .docx into the same shape the rest of the pipeline expects from a saved
    HTML page: a full document whose <head> carries the Word core properties as meta
    tags (so the docx adapter reads them like any CMS) and whose <body> wraps the
    converted content in <article>. Embedded images are extracted to a temp dir, which
    is returned as base_dir so download_images() copies them locally. Returns
    (html, base_dir).
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


# ── Footnotes ─────────────────────────────────────────────────────────────────


def convert_footnotes(soup):
    """
    Convert Ghost/HTML footnotes to Markdown footnote syntax [^n].
    Returns (soup, footnote_markdown_string).
    """
    footnote_section = soup.find("div", class_="footnotes")
    if not footnote_section:
        return soup, ""

    # Collect footnote text by id, stripping the back-link arrow
    original_notes = {}
    for li in footnote_section.find_all("li"):
        fn_id = li.get("id")
        if not fn_id:
            continue
        for a in li.find_all("a", string=re.compile(r"↩")):
            a.decompose()
        original_notes[fn_id] = li.get_text(strip=True)

    # Walk inline citations in document order
    citation_order = []
    for sup in soup.find_all("sup"):
        a = sup.find("a")
        if not a:
            continue
        href = a.get("href", "").lstrip("#")
        if href in original_notes:
            if href not in citation_order:
                citation_order.append(href)
            idx = citation_order.index(href) + 1
            sup.replace_with(f"[^{idx}]")

    footnote_section.decompose()

    md_footnotes = "\n\n"
    for i, fn_id in enumerate(citation_order, start=1):
        content = original_notes.get(fn_id, "")
        md_footnotes += f"[^{i}]: {content}\n"

    return soup, md_footnotes


# ── Embeds ────────────────────────────────────────────────────────────────────

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


# ── Metadata ──────────────────────────────────────────────────────────────────


def extract_metadata_ghost(soup):
    """
    Ghost: title, date, description, and tags come from Open Graph / meta tags;
    the cover is the first <figure> outside the gh-content body. Categories are
    left empty so build_front_matter() derives one from the first tag.
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


def extract_metadata_wordpress(soup):
    """
    WordPress, generalized across themes. Title, date, tags, and categories each
    resolve from the first source that works, so the adapter is not tied to one
    theme: title from .entry-title → og:title → h1; date from
    <meta article:published_time> → <time datetime> → .post-date/.entry-date text;
    tags from the yaaburnee tag-* classes on <article>; categories from the
    .entry-meta post-category badge. Description is left empty (WP themes rarely
    emit a per-post one) and derived from the first body paragraph in process_url().
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


def clean_content_ghost(article):
    """Cleaning pipeline for Ghost article bodies."""
    article = clean_ghost_classes(article)
    article = normalize_headings(article)
    return article


def clean_content_wordpress(article):
    """Cleaning pipeline for yaaburnee WordPress article bodies."""
    article = clean_wordpress_cruft(article)
    article = clean_ghost_classes(article)  # harmless; drops any stray gh-/kg- classes
    article = normalize_headings(article)
    return article


def extract_metadata_generic(soup):
    """
    Best-effort metadata for an arbitrary HTML page with no recognized CMS. Reads
    the conventions almost every theme/SSG emits: Open Graph tags, then common
    title/date/description elements. Tags and categories are left empty.
    """
    # Title: og:title → .entry-title → h1 → <title>
    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title:
        for el in (soup.find(class_="entry-title"), soup.find("h1"), soup.find("title")):
            if el and el.get_text(strip=True):
                title = el.get_text(strip=True)
                break
    title = title or "Untitled"

    # Date: meta published_time → .post-date/.entry-date → <time datetime>
    date = None
    date_candidates = []
    meta_pub = soup.find("meta", property="article:published_time")
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

    # Description: og:description → meta description
    description = ""
    for m in (
        soup.find("meta", property="og:description"),
        soup.find("meta", {"name": "description"}),
    ):
        if m and m.get("content"):
            description = m["content"].strip()
            break

    # Cover: og:image
    cover = ""
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        cover = og_img["content"].strip()

    return title, date, description, [], cover, []


def clean_content_generic(article):
    """Generic body cleanup: drop non-content landmarks, then the shared scrubbers."""
    for el in article.find_all(["nav", "aside", "header", "footer", "form"]):
        el.decompose()
    article = clean_wordpress_cruft(article)  # also covers generic WP share/related plugins
    article = clean_ghost_classes(article)
    article = normalize_headings(article)
    return article


def clean_content_docx(article):
    """
    Cleaning pipeline for Word-converted bodies. Drops the leading heading (it
    becomes the front-matter title, so keeping it duplicates the title in the body)
    and the empty bookmark anchors (<a id="_Hlk…"></a>) Word/mammoth leave behind.
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


def detect_docx(soup):
    """True for the wrapped HTML docx_to_html() produces (marker generator meta)."""
    gen = soup.find("meta", attrs={"name": "generator"})
    return bool(gen and "docx" in gen.get("content", "").lower())


def detect_ghost(soup):
    """True if the page looks like a Ghost export."""
    if soup.find("section", class_=re.compile("gh-content")):
        return True
    gen = soup.find("meta", attrs={"name": "generator"})
    return bool(gen and gen.get("content", "").lower().startswith("ghost"))


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


# ── ProBoards (forum threads) ─────────────────────────────────────────────────
# ProBoards/YaBB-lineage forums render each post as a table row: a 20%-width author
# cell (windowbg/windowbg2) plus an 80%-width body cell. The date sits in a
# "« Reply #N on <date> »" header, and the message is bounded by ProBoards'
# google_ad_section comments after an <hr>. A thread is a conversation, so the
# adapter rebuilds it as attributed blocks (author — date, then the message as a
# blockquote) rather than flattening it into one article (the *thread* content model).

PB_DATE_RE = re.compile(r"on ([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}[ap]m)")


def detect_proboards(soup):
    """True for a ProBoards/YaBB-lineage forum thread page."""
    has_posts = bool(soup.find("td", class_=re.compile(r"\bwindowbg2?\b")))
    has_authors = bool(soup.select_one('a[href*="viewprofile"]'))
    return has_posts and has_authors


def _proboards_message(body_cell):
    """Extract just the message HTML from a post body cell, dropping the subject/date
    header and the footer (Logged/signature). Returns a fresh <div> fragment or None."""
    msg_cell = body_cell.find("td", attrs={"colspan": True})
    if not msg_cell:
        return None
    out = BeautifulSoup("<div></div>", "html.parser")
    div = out.div
    started = False
    for node in msg_cell.children:
        if getattr(node, "name", None) == "hr":
            if not started:
                started = True  # first <hr> opens the message
                continue
            break  # a second <hr> marks the footer — stop before it
        if started:
            div.append(copy.copy(node))
    return div if div.contents else None


def _proboards_posts(root):
    """Parse a ProBoards thread into [{author, subject, date, message}] in order."""
    posts = []
    for body in root.find_all("td"):
        cls = body.get("class") or []
        if body.get("width") != "80%" or not any(c in ("windowbg", "windowbg2") for c in cls):
            continue
        row = body.find_parent("tr")
        author = None
        if row:
            info = row.find("td", attrs={"width": "20%"})
            if info:
                tag = info.find("a", href=re.compile("viewprofile")) or info.find("b")
                author = tag.get_text(strip=True) if tag else None
        subj_b = body.find("b")
        dm = PB_DATE_RE.search(body.get_text(" ", strip=True))
        posts.append(
            {
                "author": author,
                "subject": subj_b.get_text(strip=True) if subj_b else None,
                "date": dm.group(1) if dm else None,
                "message": _proboards_message(body),
            }
        )
    return posts


def _proboards_date_iso(value):
    try:
        return dateparser.parse(value).strftime("%Y-%m-%d")
    except (ValueError, TypeError, OverflowError):
        return ""


def extract_metadata_proboards(soup):
    """Title/date/description from a ProBoards thread (its first post)."""
    posts = _proboards_posts(soup)
    first = posts[0] if posts else {}
    title = first.get("subject")
    if not title and soup.title:
        t = soup.title.get_text(strip=True)
        title = t.rsplit(" - ", 1)[-1] if " - " in t else t
    date = _proboards_date_iso(first.get("date")) if first.get("date") else ""
    description = ""
    if first.get("message"):
        text = re.sub(r"\s+", " ", first["message"].get_text(" ", strip=True))
        description = text[:160].rsplit(" ", 1)[0] + "…" if len(text) > 160 else text
    return (title or "ProBoards Thread", date, description, [], "", [])


def clean_content_proboards(article):
    """Rebuild the thread as attributed blocks: 'author — date' + the message body."""
    out = BeautifulSoup("<div></div>", "html.parser")
    div = out.div
    for p in _proboards_posts(article):
        head = out.new_tag("p")
        strong = out.new_tag("strong")
        strong.string = p["author"] or "Unknown"
        head.append(strong)
        if p["date"]:
            head.append(f" — {p['date']}")
        div.append(head)
        quote = out.new_tag("blockquote")
        if p["message"]:
            quote.append(p["message"])
        div.append(quote)
    return div


# Platform adapters: each registers how to detect the platform, find metadata,
# locate the article body, and clean it. Adding a new platform/theme means adding
# one entry here (and an extract/clean/detect function); auto-detection and the
# --platform flag pick it up automatically.
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
        # td-/article-content cover a few more. process_url falls back to <article>.
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


def build_front_matter(meta):
    """Jekyll-compatible YAML front matter from a metadata dict (the jekyll target)."""
    title = meta["title"]
    date = meta.get("date")
    description = meta.get("description")
    tags = meta.get("tags") or []
    cover = meta.get("cover")
    categories = meta.get("categories")
    safe_title = title.replace('"', '\\"')
    lines = [
        "---",
        "layout: post",
        f'title: "{safe_title}"',
    ]
    if date:
        lines.append(f"date: {date} 00:00:00 +0000")
    if description:
        safe_desc = description.replace('"', '\\"')
        lines.append(f'description: "{safe_desc}"')
    if cover:
        lines.append(f"image:\n  path: {cover}")
    if tags:
        lines.append("tags:")
        for t in tags:
            lines.append(f"  - {slugify(t)}")
    # Categories: prefer explicit ones (WordPress), else fall back to the first tag
    if not categories and tags:
        categories = [tags[0]]
    if categories:
        lines.append("categories:")
        for c in categories:
            lines.append(f"  - {slugify(c)}")
    lines.append("---\n")
    return "\n".join(lines) + "\n"


# ── Output targets ────────────────────────────────────────────────────────────
# An output target decides how a converted post is written: front-matter format,
# file naming/layout, asset paths, and any Markdown-flavor tweaks. The conversion
# core stays target-agnostic (it produces metadata + body + assets), so supporting
# another static-site generator means adding one TARGETS entry. Each supplies:
#   doc_relpath(slug, date) → path (under OUTPUT_DIR) for the document file
#   asset_dir(slug)         → dir  (under OUTPUT_DIR) holding that post's images
#   asset_url(slug, fname)  → the in-document URL for a localized image
#   front_matter(meta)      → the front-matter block
#   flavor(markdown)        → post-process the Markdown body


def escape_table_pipes(markdown):
    """Escape | inside link text so kramdown/GFM won't read it as table syntax."""
    return re.sub(
        r"\[([^\]]*\|[^\]]*)\]",
        lambda m: "[" + m.group(1).replace("|", r"\|") + "]",
        markdown,
    )


def commonmark_front_matter(meta):
    """Minimal, SSG-neutral YAML front matter (no Jekyll-specific keys)."""
    safe_title = meta["title"].replace('"', '\\"')
    lines = ["---", f'title: "{safe_title}"']
    if meta.get("date"):
        lines.append(f"date: {meta['date']}")
    if meta.get("description"):
        safe_desc = meta["description"].replace('"', '\\"')
        lines.append(f'description: "{safe_desc}"')
    if meta.get("tags"):
        lines.append("tags:")
        for t in meta["tags"]:
            lines.append(f"  - {slugify(t)}")
    lines.append("---\n")
    return "\n".join(lines) + "\n"


# ── Citation objects (the `data` target) ──────────────────────────────────────
# The `data` target writes each source as a provenance-stamped citation record
# (_data/sources/<id>.yml) plus its extracted content (_sources/<id>.md), and ships
# a plugin-free Jekyll include to render it. Provenance is honest by construction:
# `archived` (public Wayback permalink + timestamp), `live` (URL + access date), or
# `local` (an author's personal copy — no public link).

KIND_BY_PLATFORM = {
    "ghost": "post",
    "wordpress": "post",
    "generic": "page",
    "docx": "document",
    "proboards": "thread",
    "txt": "document",
}

CITE_INCLUDE = """{%- comment -%}
Render a source citation by id from _data/sources/.  Usage:
  {% include cite.html id="some-slug" %}
Shipped by DeadHonestCitation's `data` target; safe to edit/restyle.
{%- endcomment -%}
{%- assign s = site.data.sources[include.id] -%}
{%- if s -%}
<figure class="citation" id="cite-{{ include.id }}">
  {%- if s.screenshot %}
  <a href="{% if s.archive_url %}{{ s.archive_url }}{% else %}{{ s.source_url }}{% endif %}"><img src="{{ s.screenshot | relative_url }}" alt="{{ s.title | escape }}"></a>
  {%- endif %}
  <figcaption>
    <strong>{{ s.title | escape }}</strong>
    {%- if s.provenance == "archived" %} — <a href="{{ s.archive_url }}">archived {{ s.captured_at }}</a>
    {%- elsif s.provenance == "live" %} — <a href="{{ s.source_url }}">live</a> (accessed {{ s.captured_at }})
    {%- else %} — author's personal copy{% endif -%}
    {%- if s.note and s.note != "" %}<br>{{ s.note }}{% endif -%}
  </figcaption>
</figure>
{%- else -%}
<!-- cite: '{{ include.id }}' not found in _data/sources -->
{%- endif -%}
"""


def derive_citation(url, base_dir, platform_name, kind=None):
    """Provenance fields for a source. Honest by construction: a local copy never
    claims a public link, and an archived capture carries its real permalink + date.
    kind overrides the platform→kind map (e.g. a captured image/document)."""
    kind = kind or KIND_BY_PLATFORM.get(platform_name, "page")
    if base_dir is not None:
        # A local saved file or .docx — an author's personal copy, not public.
        return {
            "provenance": "local",
            "source_url": os.path.basename(url),
            "archive_url": None,
            "captured_at": None,
            "kind": kind,
        }
    m = WAYBACK_RE.match(url)
    if m:
        ts = re.search(r"/web/(\d{4})(\d{2})(\d{2})", url)
        captured = f"{ts.group(1)}-{ts.group(2)}-{ts.group(3)}" if ts else None
        return {
            "provenance": "archived",
            "source_url": m.group(1),
            "archive_url": url,
            "captured_at": captured,
            "kind": kind,
        }
    # A live URL fetched directly — record today's access date.
    return {
        "provenance": "live",
        "source_url": url,
        "archive_url": None,
        "captured_at": time.strftime("%Y-%m-%d"),
        "kind": kind,
    }


def _yaml_str(value):
    """Quote a scalar for safe single-line YAML."""
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def ensure_cite_include(out_dir):
    """Write the cite include once, so a site can render citations with no plugin."""
    path = os.path.join(out_dir, "_includes", "cite.html")
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(CITE_INCLUDE)


def emit_citation(out_dir, slug, meta, markdown, footnotes, cite):
    """Write the citation record + extracted content for one source; return the
    record's relpath. (The `data` target's writer.)"""
    content_rel = os.path.join("_sources", f"{slug}.md")
    content_path = os.path.join(out_dir, content_rel)
    os.makedirs(os.path.dirname(content_path), exist_ok=True)
    with open(content_path, "w", encoding="utf-8") as f:
        f.write(markdown)
        if footnotes.strip():
            f.write(footnotes)

    lines = [
        f"id: {slug}",
        f"title: {_yaml_str(meta['title'])}",
        f"kind: {cite['kind']}",
        f"provenance: {cite['provenance']}",
    ]
    if cite["source_url"]:
        lines.append(f"source_url: {_yaml_str(cite['source_url'])}")
    if cite["archive_url"]:
        lines.append(f"archive_url: {_yaml_str(cite['archive_url'])}")
    if cite["captured_at"]:
        lines.append(f"captured_at: {cite['captured_at']}")
    if meta.get("screenshot"):
        lines.append(f"screenshot: {_yaml_str(meta['screenshot'])}")
    lines.append(f"content: {_yaml_str(content_rel)}")
    lines.append('note: ""')

    yml_rel = os.path.join("_data", "sources", f"{slug}.yml")
    yml_path = os.path.join(out_dir, yml_rel)
    os.makedirs(os.path.dirname(yml_path), exist_ok=True)
    with open(yml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    ensure_cite_include(out_dir)
    return yml_rel


TARGETS = {
    "jekyll": {
        "doc_relpath": lambda slug, date: os.path.join(
            "_posts", f"{date or '0000-00-00'}-{slug}.md"
        ),
        "asset_dir": lambda slug: os.path.join("assets", "img", "blog", "posts", slug),
        "asset_url": lambda slug, fname: f"/assets/img/blog/posts/{slug}/{fname}",
        "front_matter": build_front_matter,
        "flavor": escape_table_pipes,
    },
    "commonmark": {
        "doc_relpath": lambda slug, date: f"{slug}.md",
        "asset_dir": lambda slug: os.path.join("assets", slug),
        "asset_url": lambda slug, fname: f"assets/{slug}/{fname}",
        "front_matter": commonmark_front_matter,
        "flavor": escape_table_pipes,
    },
    # Provenance-stamped citation records, not posts. Writes _data/sources/<id>.yml
    # + _sources/<id>.md via emit_citation; images go under /assets/img/sources/.
    "data": {
        "doc_relpath": lambda slug, date: os.path.join("_data", "sources", f"{slug}.yml"),
        "asset_dir": lambda slug: os.path.join("assets", "img", "sources", slug),
        "asset_url": lambda slug, fname: f"/assets/img/sources/{slug}/{fname}",
        "flavor": escape_table_pipes,
        "emit": emit_citation,
    },
}

TARGET_ALIASES = {
    "jekyll": "jekyll",
    "jk": "jekyll",
    "commonmark": "commonmark",
    "cm": "commonmark",
    "plain": "commonmark",
    "md": "commonmark",
    "data": "data",
    "citation": "data",
    "cite": "data",
}


def resolve_target(name):
    """Map a target name/alias to its TARGETS entry (defaults to jekyll)."""
    return TARGETS[TARGET_ALIASES.get(name or "jekyll", name or "jekyll")]


# ── Core ──────────────────────────────────────────────────────────────────────


def fetch(url):
    """Fetch a page through the shared polite layer (rate limit + backoff + Retry-After)."""
    return polite_get(url)


# Local file extensions the pipeline can read directly (a saved page or a Word doc).
SOURCE_EXTS = (".html", ".htm", ".docx")


def is_local_source(src):
    """True if src is a local HTML file to read rather than a URL to fetch."""
    if src.startswith(("http://", "https://")):
        return False
    return src.lower().endswith(SOURCE_EXTS) or os.path.exists(os.path.expanduser(src))


# Windows-1252 punctuation lives in 0x80–0x9F (curly quotes, en/em dashes, ellipsis).
# Pages served as text/html with no charset are decoded by `requests` as ISO-8859-1,
# which maps those same bytes to C1 control characters (e.g. a curly apostrophe 0x92
# becomes U+0092) — invisible mojibake that also makes YAML front matter unparseable.
# Latin-1 and cp1252 agree above 0x9F, so remapping just this range fully repairs the
# mislabel; on correctly-decoded UTF-8 there are no C1 chars, so it's a no-op.
_CP1252_C1_MAP = {
    code: bytes([code]).decode("cp1252", "ignore") or None for code in range(0x80, 0xA0)
}


def fix_cp1252_controls(text):
    """Repair Windows-1252 punctuation that arrived mis-decoded as C1 control chars."""
    return text.translate(_CP1252_C1_MAP)


def load_source(src):
    """
    Return (html_text, base_dir) for a source. For a local file, base_dir is its
    directory, used to resolve the sibling "<name>_files/" asset folder; for a URL,
    base_dir is None and the page is fetched over the network.
    """
    if is_local_source(src):
        path = os.path.expanduser(src)
        if path.lower().endswith(".docx"):
            return docx_to_html(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(), os.path.dirname(os.path.abspath(path))
    return fetch(src).text, None


def _dir_sources(directory, recursive, exts=SOURCE_EXTS):
    """Every source file (matching exts) inside a directory, sorted.

    Saved-page asset folders ('<name>_files/') and dotfiles are skipped — they hold
    images, not pages. With recursive, walk subdirectories too (still pruning any
    '*_files' tree and hidden dirs)."""
    found = []
    if recursive:
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.endswith("_files") and not d.startswith(".")]
            for name in files:
                if name.lower().endswith(exts) and not name.startswith("."):
                    found.append(os.path.join(root, name))
    else:
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if not name.startswith(".") and os.path.isfile(path) and name.lower().endswith(exts):
                found.append(path)
    return sorted(found)


def collect_sources(tokens, recursive=False, txt_as_content=False):
    """Resolve CLI source tokens into a flat, de-duplicated work list.

    Each token is classified independently, so one run can mix input kinds:
      - a directory            → every source file inside (recursive opt-in)
      - a URL (http/https)     → itself
      - a content file         → itself (.html/.htm/.docx page or Word doc, .md/
                                  .markdown, and .txt when txt_as_content)
      - any other existing file → a *list file*: read it, one source per non-blank,
                                  non-'#' line (the classic urls.txt — .txt stays a
                                  list file unless txt_as_content)
      - anything else          → reported missing and skipped
    This is the input-agnostic seam: the adapter registry is untouched; we only
    decide *what to feed it*."""
    content_exts = SOURCE_EXTS + MD_EXTS + ((".txt",) if txt_as_content else ())
    sources = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        expanded = os.path.expanduser(token)
        if os.path.isdir(expanded):
            hits = _dir_sources(expanded, recursive, content_exts)
            if not hits:
                print(f"  ⚠ no source files in directory: {token}")
            sources.extend(hits)
        elif token.startswith(("http://", "https://")):
            sources.append(token)
        elif token.lower().endswith(content_exts):
            # A non-URL content token is a local page/doc/markdown file; it must exist.
            if os.path.isfile(expanded):
                sources.append(expanded)
            else:
                print(f"  ⚠ source not found, skipping: {token}")
        elif os.path.isfile(expanded):
            with open(expanded, encoding="utf-8", errors="replace") as f:
                sources.extend(
                    ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")
                )
        else:
            print(f"  ⚠ source not found, skipping: {token}")
    # De-duplicate while preserving first-seen order.
    seen, unique = set(), []
    for s in sources:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def _outcome(status, output=None, reason=None):
    """A per-source result for the run log: status is converted / skipped / failed."""
    return {"status": status, "output": output, "reason": reason}


def log_run(url, outcome, target):
    """Append one source's outcome to output/runlog.jsonl (an append-only audit log —
    a record of coverage, not a database). Best-effort: never fail the run over it."""
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "url": url,
        "target": target,
        **outcome,
    }
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(RUNLOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _emit_source(
    tgt, doc_relpath, url, base_dir, platform_name, slug, meta, body, footnotes, kind=None
):
    """Write one converted source via the active target; return its relpath. Shared by
    the HTML pipeline (process_url) and the Markdown passthrough (process_markdown)."""
    if tgt.get("emit"):
        cite = derive_citation(url, base_dir, platform_name, kind=kind)
        return tgt["emit"](OUTPUT_DIR, slug, meta, body, footnotes, cite)
    filepath = os.path.join(OUTPUT_DIR, doc_relpath)
    front_matter = tgt["front_matter"](meta)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(front_matter)
        f.write(body)
        if footnotes.strip():
            f.write(footnotes)
    return doc_relpath


# ── Markdown / plain-text passthrough ─────────────────────────────────────────
# Loose .md/.markdown (and .txt under --txt) files are already in the output format,
# so they skip the HTML round-trip: read the body verbatim, lift title/date/tags from
# a YAML front-matter block if present (else the first heading or the filename), and
# emit through the active target. Provenance is 'local' (an author's own file).

MD_EXTS = (".md", ".markdown")
FM_BLOCK_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def is_markdown_source(src, md_mode=False):
    """True if a source should be handled as Markdown/plain-text passthrough."""
    if src.startswith(("http://", "https://")):
        return False
    low = src.lower()
    return low.endswith(MD_EXTS) or (md_mode and low.endswith(".txt"))


def _parse_simple_front_matter(text):
    """Split a leading YAML front-matter block from a Markdown file, lifting
    title/date/description/tags without a YAML dependency. Returns (meta, body)."""
    m = FM_BLOCK_RE.match(text)
    if not m:
        return {}, text
    block, body = m.group(1), text[m.end() :]
    meta = {}
    mt = re.search(r'^title:\s*["\']?(.*?)["\']?\s*$', block, re.M)
    if mt:
        meta["title"] = mt.group(1)
    dt = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})", block, re.M)
    if dt:
        meta["date"] = dt.group(1)
    de = re.search(r'^description:\s*["\']?(.*?)["\']?\s*$', block, re.M)
    if de:
        meta["description"] = de.group(1)
    if "tags:" in block:
        tags = re.findall(r"^\s*-\s*(.+?)\s*$", block[block.index("tags:") :], re.M)
        if tags:
            meta["tags"] = tags
    return meta, body


def _first_markdown_heading(body):
    m = re.search(r"^#{1,6}\s+(.+?)\s*$", body, re.M)
    return m.group(1).strip() if m else None


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
        return _outcome("failed", reason=f"load: {e}")
    meta_in, body = _parse_simple_front_matter(text)
    body = body.strip("\n")
    if not body.strip():
        print("  ✗ Empty file — skipping.")
        return _outcome("skipped", reason="empty file")
    stem = os.path.splitext(os.path.basename(expanded))[0]
    title = (
        meta_in.get("title")
        or _first_markdown_heading(body)
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
        return _outcome("skipped", doc_relpath, reason="exists")
    written = _emit_source(
        tgt, doc_relpath, path, os.path.dirname(expanded), "txt", slug, meta, body + "\n", ""
    )
    print(f"  ✓ Saved: {written}")
    return _outcome("converted", written)


# ── Capture tier ──────────────────────────────────────────────────────────────
# Not every source is convertible HTML. A URL whose content is a PDF, image, zip,
# etc. is captured verbatim — saved as an asset and recorded with a reference —
# rather than forced through the article pipeline or dropped. Completeness over
# cleanliness: every source ends converted, captured, or failed (never silent).

MARKUP_TYPES = ("text/html", "application/xhtml", "application/xml", "text/xml")


def _is_markup(content_type):
    """True if a Content-Type should go through the HTML pipeline."""
    ct = (content_type or "").split(";")[0].strip().lower()
    return (not ct) or ct.startswith(MARKUP_TYPES) or ct.endswith("+xml")


def _capture_kind(content_type):
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if "pdf" in ct or ct.startswith(("application/msword", "application/vnd")):
        return "document"
    return "file"


def capture_binary(content, content_type, url, tgt):
    """Preserve a non-HTML source verbatim: save the bytes as an asset and emit a
    record that references them. Returns an outcome dict."""
    original = unwrap_wayback(url)
    name = os.path.basename(urlparse(original).path) or "capture"
    slug = slugify(os.path.splitext(name)[0]) or "capture"
    kind = _capture_kind(content_type)

    asset_dir = os.path.join(OUTPUT_DIR, tgt["asset_dir"](slug))
    os.makedirs(asset_dir, exist_ok=True)
    with open(os.path.join(asset_dir, name), "wb") as f:
        f.write(content)
    asset_url = tgt["asset_url"](slug, name)

    body = f"![{name}]({asset_url})\n" if kind == "image" else f"[{name}]({asset_url})\n"
    meta = {
        "title": name,
        "date": "",
        "description": f"Captured {kind}: {name}",
        "tags": [],
        "cover": "",
        "categories": [],
    }
    doc_relpath = tgt["doc_relpath"](slug, None)
    if os.path.exists(os.path.join(OUTPUT_DIR, doc_relpath)):
        print(f"  ↷ Already exists, skipping: {doc_relpath}")
        return _outcome("skipped", doc_relpath, reason="exists")
    written = _emit_source(tgt, doc_relpath, url, None, "capture", slug, meta, body, "", kind=kind)
    print(f"  ✓ Captured ({kind}): {written}")
    return _outcome("captured", written, reason=kind)


def screenshot_page(url, out_path, timeout=30000):
    """Render a page to a PNG with a headless browser. Returns True on success.
    Playwright is imported lazily and is optional — like mammoth for .docx — so the
    core install stays light; a screenshot just no-ops with a hint when it's absent."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "  ⚠ screenshots need playwright: pip install playwright && playwright install chromium"
        )
        return False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout)
            page.screenshot(path=out_path, full_page=True)
            browser.close()
        return True
    except Exception as e:
        print(f"  ⚠ screenshot failed: {e}")
        return False


def process_url(url, platform=None, target=None, screenshot=False):
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
            return _outcome("failed", reason=f"load: {e}")
    else:
        try:
            resp = polite_get(url)
        except Exception as e:
            print(f"  ✗ Failed to load: {e}")
            return _outcome("failed", reason=f"load: {e}")
        base_dir = None
        content_type = resp.headers.get("Content-Type", "")
        if not _is_markup(content_type):
            return capture_binary(resp.content, content_type, url, tgt)
        html = resp.text

    html = fix_cp1252_controls(html)
    soup = BeautifulSoup(html, "html.parser")
    soup = remove_wayback_toolbar(soup)

    resolved = platform or detect_platform(soup)
    if resolved is None:
        print("  ✗ Could not detect platform — re-run with --platform; skipping.")
        return _outcome("failed", reason="platform not detected")
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
        return _outcome("skipped", reason="no article content")

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
        return _outcome("skipped", doc_relpath, reason="exists")

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
        return _outcome("skipped", reason="empty body")

    meta = {
        "title": title,
        "date": date,
        "description": description,
        "tags": tags,
        "cover": local_cover,
        "categories": categories,
    }

    # Screenshots are evidence for citations: render the page to an asset and let the
    # data target reference it. Best-effort; needs playwright.
    if screenshot and tgt.get("emit"):
        shot_dir = os.path.join(OUTPUT_DIR, tgt["asset_dir"](slug))
        os.makedirs(shot_dir, exist_ok=True)
        shot_name = f"{slug}-screenshot.png"
        if screenshot_page(url, os.path.join(shot_dir, shot_name)):
            meta["screenshot"] = tgt["asset_url"](slug, shot_name)

    written = _emit_source(
        tgt, doc_relpath, url, base_dir, resolved, slug, meta, markdown, md_footnotes
    )
    print(f"  ✓ Saved: {written}")
    for note in embed_notes:
        print(f"  ⚠ NEEDS REVIEW: {note}")
    return _outcome("converted", written, reason="; ".join(embed_notes) or None)


# ── Output housekeeping ───────────────────────────────────────────────────────


def post_slug(path):
    """Slug of an output post file (its name minus the YYYY-MM-DD- prefix and .md)."""
    m = re.match(r"\d{4}-\d{2}-\d{2}-(.+)\.md$", os.path.basename(path))
    return m.group(1) if m else re.sub(r"\.md$", "", os.path.basename(path))


def clean_output(assume_yes=False):
    """Delete everything under output/ (posts + per-post asset folders)."""
    posts = sorted(glob.glob(os.path.join(POSTS_DIR, "*.md")))
    assets = [d for d in glob.glob(os.path.join(ASSETS_DIR, "*")) if os.path.isdir(d)]
    if not posts and not assets:
        print("output/ is already clean.")
        return
    print(f"This deletes {len(posts)} post(s) and {len(assets)} asset folder(s) under output/.")
    if not assume_yes:
        try:
            if input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
                print("Aborted.")
                return
        except EOFError:
            print("Aborted.")
            return
    for p in posts:
        os.remove(p)
    for d in assets:
        shutil.rmtree(d, ignore_errors=True)
    print(f"✓ Cleaned output/ ({len(posts)} post(s), {len(assets)} asset folder(s)).")


def prune_output():
    """Remove stale output: older duplicates of a slug, and orphaned asset folders
    (an asset folder whose slug no longer has a post). Keeps the newest per slug."""
    posts = glob.glob(os.path.join(POSTS_DIR, "*.md"))
    by_slug = {}
    for p in posts:
        by_slug.setdefault(post_slug(p), []).append(p)
    removed = 0
    for slug, files in by_slug.items():
        if len(files) > 1:
            files.sort(key=os.path.getmtime, reverse=True)  # newest first
            for old in files[1:]:
                print(f"  ↺ older duplicate of '{slug}', removing: {os.path.basename(old)}")
                os.remove(old)
                removed += 1
    live = set(by_slug)
    for d in glob.glob(os.path.join(ASSETS_DIR, "*")):
        if os.path.isdir(d) and os.path.basename(d) not in live:
            print(f"  ↺ orphaned assets (no post), removing: {os.path.basename(d)}/")
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    print(f"✓ Prune complete — {removed} item(s) removed." if removed else "✓ Nothing to prune.")


def main():
    parser = argparse.ArgumentParser(
        description="Convert archived blog posts into Jekyll Markdown. A source is a "
        "Wayback/live URL, a saved HTML page or Word .docx (its sibling "
        "'<name>_files/' folder supplies images), a directory of those, or "
        "a list-file of any of the above one per line."
    )
    parser.add_argument(
        "sources",
        nargs="*",
        default=["urls.txt"],
        help="One or more sources: a directory (every .html/.htm/.docx inside), a "
        "saved page (.html/.htm), a Word doc (.docx), a Wayback/live URL, or a "
        "list-file of any of those one per line (default: urls.txt).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="When a source is a directory, recurse into subdirectories "
        "(skips saved-page '<name>_files/' asset folders).",
    )
    parser.add_argument(
        "--platform",
        "-p",
        default=None,
        choices=sorted(set(PLATFORMS) | set(PLATFORM_ALIASES)),
        help="Force the source platform / theme instead of auto-detecting. "
        "Accepts: ghost (gh), wordpress (wp, yaaburnee), generic (html).",
    )
    # Convenience flags equivalent to --platform <name>
    parser.add_argument(
        "--ghost",
        dest="platform",
        action="store_const",
        const="ghost",
        help="Shorthand for --platform ghost",
    )
    parser.add_argument(
        "--wordpress",
        "--yaaburnee",
        dest="platform",
        action="store_const",
        const="wordpress",
        help="Shorthand for --platform wordpress",
    )
    parser.add_argument(
        "--generic",
        "--html",
        dest="platform",
        action="store_const",
        const="generic",
        help="Shorthand for --platform generic (arbitrary HTML pages)",
    )
    parser.add_argument(
        "--docx",
        "--word",
        dest="platform",
        action="store_const",
        const="docx",
        help="Shorthand for --platform docx (Word .docx files)",
    )
    parser.add_argument(
        "--txt",
        "--markdown",
        dest="markdown",
        action="store_true",
        help="Treat .txt inputs as Markdown/plain-text content (passthrough) instead "
        "of as a list-file of sources. (.md/.markdown are always passthrough.)",
    )
    parser.add_argument(
        "--target",
        "-t",
        default="jekyll",
        choices=sorted(set(TARGETS) | set(TARGET_ALIASES)),
        help="Output format/layout (default: jekyll). Accepts: jekyll (jk), "
        "commonmark (cm, plain, md), data (citation objects).",
    )
    parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Render each page to a PNG and reference it from its citation "
        "(--target data; needs playwright).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete all generated output (posts + assets) and exit.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove stale output (older slug duplicates, orphaned assets) and exit.",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompts (e.g. for --clean)."
    )
    args = parser.parse_args()

    # Housekeeping actions run on their own and exit.
    if args.clean:
        clean_output(assume_yes=args.yes)
        return
    if args.prune:
        prune_output()
        return

    # None ⇒ auto-detect per source from the page markup
    platform = PLATFORM_ALIASES.get(args.platform, args.platform)
    md_mode = args.markdown

    sources = collect_sources(args.sources, recursive=args.recursive, txt_as_content=md_mode)
    if not sources:
        print("No sources to process.")
        sys.exit(0)

    target = TARGET_ALIASES.get(args.target, args.target)
    mode = f"as '{platform}'" if platform else "auto-detecting platform"
    print(f"Processing {len(sources)} source(s), {mode}, → {target}…")
    tally = {}
    for src in sources:
        if is_markdown_source(src, md_mode):
            result = process_markdown(src, target)
        else:
            result = process_url(src, platform, target, screenshot=args.screenshot)
        result = result or _outcome("failed", reason="no result")
        log_run(src, result, target)
        tally[result["status"]] = tally.get(result["status"], 0) + 1

    summary = ", ".join(f"{n} {status}" for status, n in sorted(tally.items()))
    print(f"\nDone — {summary or 'nothing processed'}.")
    print(f"Run log: {RUNLOG}")


if __name__ == "__main__":
    main()
