"""Last-resort adapter for arbitrary HTML pages with no recognized CMS."""

from dateutil import parser as dateparser

from ..transform.cleanup import clean_ghost_classes, clean_wordpress_cruft, normalize_headings


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
