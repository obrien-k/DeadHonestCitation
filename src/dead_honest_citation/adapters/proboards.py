"""
ProBoards (forum threads) adapter — the *thread* content model.

ProBoards/YaBB-lineage forums render each post as a table row: a 20%-width author
cell (windowbg/windowbg2) plus an 80%-width body cell. The date sits in a
"« Reply #N on <date> »" header, and the message is bounded by ProBoards'
google_ad_section comments after an <hr>. A thread is a conversation, so the
adapter rebuilds it as attributed blocks (author — date, then the message as a
blockquote) rather than flattening it into one article.
"""

import copy
import datetime as dt
import re
from collections.abc import Sequence  # noqa: I001
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from dateutil import parser as dateparser

from ..models import PostMetadata
from ..network.polite import polite_get
from ..network.wayback import WAYBACK_RE
from ..transform.encoding import fix_cp1252_controls
from ..ui import warn
from .base import PlatformAdapter, Selector, as_tag, attr_str

PB_DATE_RE = re.compile(r"on ([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}[ap]m)")


@dataclass
class PBPost:
    """One parsed forum post: attribution plus the message fragment.

    `date` is the board's display string ("Mar 14, 2005, 9:12pm"), kept verbatim
    for the attributed rendering; parse it with _proboards_date() when a real
    date is needed.
    """

    author: str | None
    subject: str | None
    date: str | None
    message: Tag | None


class ProBoardsAdapter(PlatformAdapter):
    """Forum threads. No <article>/<main>; the whole <body> is the content root,
    rebuilt into attributed author/date blocks. Detection is structural
    (windowbg cells + viewprofile links)."""

    name: ClassVar[str] = "proboards"
    content: ClassVar[Selector | list[Selector]] = ("body", {})
    kind: ClassVar[str] = "thread"
    is_thread: ClassVar[bool] = True
    thread_shot_selector: ClassVar[str | None] = (
        'td[width="80%"].windowbg, td[width="80%"].windowbg2'
    )

    def detect(self, soup: BeautifulSoup) -> bool:
        """True for a ProBoards/YaBB-lineage forum thread page."""
        has_posts = bool(soup.find("td", class_=re.compile(r"\bwindowbg2?\b")))
        has_authors = bool(soup.select_one('a[href*="viewprofile"]'))
        return has_posts and has_authors

    def extract_metadata(self, soup: BeautifulSoup) -> PostMetadata:
        """Title/date/description from a ProBoards thread (its first post)."""
        posts = _proboards_posts(soup)
        first = posts[0] if posts else None
        title = first.subject if first else None
        if not title:
            title_el = soup.title
            if title_el:
                t = title_el.get_text(strip=True)
                title = t.rsplit(" - ", 1)[-1] if " - " in t else t
        date = _proboards_date(first.date) if first and first.date else None
        description = ""
        if first and first.message:
            text = re.sub(r"\s+", " ", first.message.get_text(" ", strip=True))
            description = text[:160].rsplit(" ", 1)[0] + "…" if len(text) > 160 else text
        return PostMetadata(title=title or "ProBoards Thread", date=date, description=description)

    def clean(self, article: Tag, full_thread: bool = False) -> Tag:
        """Rebuild a ProBoards thread as attributed blocks ('author — date' + message).

        Default: the original post only; full_thread keeps every post on the
        page. (The live paginated crawl lives in proboards_collect, which has
        the source URL.)
        """
        posts = _proboards_posts(article)
        return proboards_render(posts if full_thread else posts[:1])

    def render_thread(self, article: Tag, url: str, base_dir: str | None, full_thread: bool) -> Tag:
        """Thread entry point — full_thread also crawls the live thread's later pages."""
        return proboards_render(proboards_collect(article, url, base_dir, full_thread))


def _proboards_message(body_cell: Tag) -> Tag | None:
    """Extract just the message HTML from a post body cell, dropping the subject/date
    header and the footer (Logged/signature). Returns a fresh <div> fragment or None."""
    msg_cell = as_tag(body_cell.find("td", attrs={"colspan": True}))
    if not msg_cell:
        return None
    out = BeautifulSoup("<div></div>", "html.parser")
    div = out.div
    assert div is not None
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


def _proboards_posts(root: Tag) -> list[PBPost]:
    """Parse a ProBoards thread into its posts, in page order."""
    posts = []
    for body in root.find_all("td"):
        cls: Sequence[str] = body.get("class") or []
        if body.get("width") != "80%" or not any(c in ("windowbg", "windowbg2") for c in cls):
            continue
        row = body.find_parent("tr")
        author = None
        if row:
            info = as_tag(row.find("td", attrs={"width": "20%"}))
            if info:
                tag = info.find("a", href=re.compile("viewprofile")) or info.find("b")
                author = tag.get_text(strip=True) if tag else None
        subj_b = body.find("b")
        dm = PB_DATE_RE.search(body.get_text(" ", strip=True))
        posts.append(
            PBPost(
                author=author,
                subject=subj_b.get_text(strip=True) if subj_b else None,
                date=dm.group(1) if dm else None,
                message=_proboards_message(body),
            )
        )
    return posts


def _proboards_date(value: str | None) -> dt.date | None:
    try:
        return dateparser.parse(value).date() if value else None
    except (ValueError, TypeError, OverflowError):
        return None


def proboards_render(posts: list[PBPost]) -> Tag:
    """Build attributed blocks ('author — date' + message blockquote) from parsed posts."""
    out = BeautifulSoup("<div></div>", "html.parser")
    div = out.div
    assert div is not None
    for p in posts:
        head = out.new_tag("p")
        strong = out.new_tag("strong")
        strong.string = p.author or "Unknown"
        head.append(strong)
        if p.date:
            head.append(f" — {p.date}")
        div.append(head)
        quote = out.new_tag("blockquote")
        if p.message:
            quote.append(p.message)
        div.append(quote)
    return div


def _proboards_next_pages(root: Tag, base_url: str) -> list[str]:
    """Best-effort discovery of a *live* ProBoards thread's later-page URLs from its
    pagination nav: anchors whose visible text is a bare page number ≥ 2. Returns
    absolute URLs in page order, de-duplicated. Archived/local captures don't use this
    (the Wayback snapshot rarely includes every page), so the thread stays single-page."""
    seen, pages = set(), []
    for a in root.find_all("a", href=True):
        txt = a.get_text(strip=True)
        if not txt.isdigit() or int(txt) < 2:
            continue
        href = urljoin(base_url, attr_str(as_tag(a), "href"))
        if href in seen:
            continue
        seen.add(href)
        pages.append((int(txt), href))
    return [href for _, href in sorted(pages)]


def proboards_collect(root: Tag, url: str, base_dir: str | None, full_thread: bool) -> list[PBPost]:
    """Posts for a ProBoards source under the forum model.

    Default: the original post only — a forum citation is anchored to the OP,
    with the rest of the thread available at the source. full_thread keeps
    every post on the page; and for a *live* source it also crawls the
    remaining paginated pages (archived/local stay at 1).

    Args:
        root: The thread page's content root (its <body>).
        url: The source URL/path, used to absolutize pagination links and to
            distinguish live from archived.
        base_dir: Directory of a local saved page, or None for a fetched URL.
        full_thread: Keep every post (and crawl a live thread's later pages).
    """
    posts = _proboards_posts(root)
    if not full_thread:
        return posts[:1]
    is_live = base_dir is None and not WAYBACK_RE.match(url)
    if is_live:
        for page_url in _proboards_next_pages(root, url):
            try:
                html = fix_cp1252_controls(polite_get(page_url).text)
            except Exception as e:
                warn(f"  ⚠ full-thread: could not fetch {page_url}: {e}")
                break
            posts.extend(_proboards_posts(BeautifulSoup(html, "html.parser")))
    return posts
