import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from slugify import slugify
from dateutil import parser as dateparser
from urllib.parse import urlparse

OUTPUT_DIR = "output"
POSTS_DIR = os.path.join(OUTPUT_DIR, "_posts")
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets", "img", "blog", "posts")
WAYBACK_RE = re.compile(r"(?:https?://web\.archive\.org)?/web/\d+(?:im_)?/(https?://.+)")

def unwrap_wayback(url):
    m = WAYBACK_RE.match(url)
    return m.group(1) if m else url

os.makedirs(POSTS_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ghost-2-md/1.0)"
}

def clean_ghost_classes(soup):
    """Strip Ghost/Koenig CSS classes and data attributes from all tags."""
    for tag in soup.find_all(True):
        if tag.has_attr("class"):
            tag["class"] = [
                c for c in tag["class"]
                if not c.startswith(("gh-", "kg-"))
            ]
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

def download_image(url, post_img_dir):
    """Download a single image to post_img_dir. Returns the local path, or None on failure."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        filename = os.path.basename(urlparse(url).path) or "image"
        local_path = os.path.join(post_img_dir, filename)
        with open(local_path, "wb") as f:
            f.write(response.content)
        return local_path
    except Exception as e:
        print(f"  ⚠ Image download failed ({url}): {e}")
        return None


def download_cover(cover_url, slug):
    """Download the cover image and return its local asset path, or '' on failure."""
    if not cover_url:
        return ""
    post_img_dir = os.path.join(ASSETS_DIR, slug)
    os.makedirs(post_img_dir, exist_ok=True)

    if cover_url.startswith("/web/"):
        cover_url = "https://web.archive.org" + cover_url

    m = WAYBACK_RE.match(cover_url)
    if m:
        ts_match = re.match(r"(?:https?://web\.archive\.org)?/web/(\d+)", cover_url)
        timestamp = ts_match.group(1) if ts_match else ""
        original = m.group(1)
        candidates = (
            [f"https://web.archive.org/web/{timestamp}im_/{original}", original]
            if timestamp else [cover_url, original]
        )
    else:
        candidates = [cover_url]

    for url in candidates:
        local_path = download_image(url, post_img_dir)
        if local_path:
            filename = os.path.basename(local_path)
            return f"/assets/img/blog/posts/{slug}/{filename}"

    return ""


def download_images(soup, slug):
    """
    Download all images in the article and rewrite their src to local paths.
    Skips images that are already local (e.g. already rewritten on a re-run).
    """
    post_img_dir = os.path.join(ASSETS_DIR, slug)
    os.makedirs(post_img_dir, exist_ok=True)

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src or src.startswith("/assets"):
            continue

        # Normalize relative Wayback paths (/web/TIMESTAMP/...) to full URLs
        if src.startswith("/web/"):
            src = "https://web.archive.org" + src

        m = WAYBACK_RE.match(src)
        if m:
            original = m.group(1)
            ts_match = re.match(r"(?:https?://web\.archive\.org)?/web/(\d+)", src)
            timestamp = ts_match.group(1) if ts_match else ""
            candidates = (
                [f"https://web.archive.org/web/{timestamp}im_/{original}", original]
                if timestamp else [src, original]
            )
        else:
            candidates = [src]

        for url in candidates:
            local_path = download_image(url, post_img_dir)
            if local_path:
                filename = os.path.basename(local_path)
                img["src"] = f"/assets/img/blog/posts/{slug}/{filename}"
                break

    return soup

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


# ── Metadata ──────────────────────────────────────────────────────────────────

def extract_metadata(soup):
    """
    Pull title, publish date, description, and tags from Open Graph / meta tags.
    Falls back to the first h1 for the title if OG tags are absent.
    """
    # Title: prefer OG, fall back to first h1
    og_title = soup.find("meta", property="og:title")
    title = og_title["content"] if og_title else None
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else "Untitled"

    # Date
    date_meta = (
        soup.find("meta", property="article:published_time")
        or soup.find("meta", {"name": "published_time"})
    )
    date = None
    if date_meta and date_meta.get("content"):
        try:
            date = dateparser.parse(date_meta["content"]).date()
        except Exception:
            pass

    # Description
    desc_meta = (
        soup.find("meta", property="og:description")
        or soup.find("meta", {"name": "description"})
    )
    description = desc_meta["content"].strip() if desc_meta and desc_meta.get("content") else ""

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

    return title, date, description, tags, cover


def build_front_matter(title, date, description, tags, cover):
    """Emit a Jekyll-compatible YAML front matter block."""
    # Escape any quotes in the title
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
        lines.append("categories:")
        lines.append(f"  - {slugify(tags[0])}")
    lines.append("---\n")
    return "\n".join(lines) + "\n"

# ── Core ──────────────────────────────────────────────────────────────────────

def fetch(url, retries=3, delay=2):
    """GET with simple retry logic for Wayback Machine rate limiting."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if attempt < retries - 1:
                print(f"  Retrying ({attempt + 1}/{retries - 1})…")
                time.sleep(delay * (attempt + 1))
            else:
                raise e

def process_url(url):
    print(f"\n→ {url}")
    try:
        response = fetch(url)
    except Exception as e:
        print(f"  ✗ Failed to fetch: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    soup = remove_wayback_toolbar(soup)

    # Extract metadata before unwrapping so cover img src retains its Wayback timestamp
    title, date, description, tags, cover = extract_metadata(soup)

    for a in soup.find_all("a", href=True):
        a["href"] = unwrap_wayback(a["href"])
    for img in soup.find_all("img", src=True):
        img["src"] = unwrap_wayback(img["src"])

    # Ghost stores the article in a <section> with a gh-content class
    article = soup.find("section", class_=re.compile("gh-content"))
    if not article:
        # Fallback: try <article> or <main>
        article = soup.find("article") or soup.find("main")
    if not article:
        print("  ✗ No article content found — skipping.")
        return

    slug = slugify(title)
    local_cover = download_cover(cover, slug)
    date_prefix = str(date) if date else "0000-00-00"
    filename = f"{date_prefix}-{slug}.md"
    filepath = os.path.join(POSTS_DIR, filename)

    if os.path.exists(filepath):
        print(f"  ↷ Already exists, skipping: {filename}")
        return

    article = clean_ghost_classes(article)
    article = normalize_headings(article)
    article = download_images(article, slug)
    article, md_footnotes = convert_footnotes(article)

    markdown = md(str(article), heading_style="ATX", bullets="-")
    front_matter = build_front_matter(title, date, description, tags, local_cover)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(front_matter)
        f.write(markdown)
        if md_footnotes.strip():
            f.write(md_footnotes)

    print(f"  ✓ Saved: {filename}")

def main():
    urls_file = sys.argv[1] if len(sys.argv) > 1 else "urls.txt"

    if not os.path.exists(urls_file):
        print(f"Error: '{urls_file}' not found.")
        sys.exit(1)

    with open(urls_file) as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not urls:
        print("No URLs to process.")
        sys.exit(0)

    print(f"Processing {len(urls)} URL(s)…")
    for url in urls:
        process_url(url)
    print("\nDone.")

if __name__ == "__main__":
    main()
