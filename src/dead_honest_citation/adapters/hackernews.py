"""
Hacker News (news.ycombinator.com) adapter — the *thread* content model.

An HN item page is one submission plus a comment tree, rendered as nested tables.
The submission lives in `table.fatitem`: `.titleline > a` carries the title and
the outbound link, `.subtext` the score/author/age, and `.toptext` the self-text
of an Ask/Show/Tell HN. Comments are `tr.athing.comtr` rows whose `td.ind[indent]`
encodes depth and whose `.commtext` holds the body.

Like the forum adapter this is a conversation, not an article, so it rebuilds the
page into attributed blocks. Original-post model: only the submission is kept
unless --full-thread, because the submission is what a citation anchors to.
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import ClassVar

from bs4 import BeautifulSoup, Tag
from dateutil import parser as dateparser

from ..models import PostMetadata
from .base import PlatformAdapter, Selector, as_tag, attr_str

# HN's <span class="age" title="2026-02-17T15:36:46 1771342606"> — ISO stamp, then
# a unix epoch. Only the leading ISO half is a date.
_AGE_TITLE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T[\d:]+)")
# "Show HN: ...", "Ask HN: ...", "Tell HN: ..." — HN's own submission taxonomy.
_HN_PREFIX_RE = re.compile(r"^(Show|Ask|Tell) HN:", re.I)


@dataclass
class HNComment:
    """One comment: attribution, tree depth, and the message fragment."""

    author: str | None
    date: str | None
    depth: int
    body: Tag | None


@dataclass
class HNStory:
    """The submission itself — the citation anchor of an HN thread."""

    title: str = "Untitled"
    target_url: str = ""
    site: str = ""
    author: str | None = None
    date: dt.date | None = None
    posted_at: str | None = None
    points: str = ""
    comment_count: str = ""
    text: Tag | None = None
    comments: list[HNComment] = field(default_factory=list)


def _age_date(age: Tag | None) -> tuple[dt.date | None, str | None]:
    """The (date, ISO stamp) from an `.age` span's title attribute."""
    m = _AGE_TITLE_RE.match(attr_str(age, "title"))
    if not m:
        return None, None
    try:
        return dateparser.parse(m.group(1)).date(), m.group(1)
    except Exception:
        return None, m.group(1)


def parse_story(root: Tag) -> HNStory:
    """Parse the submission out of an HN item page."""
    story = HNStory()
    fat = as_tag(root.find(class_="fatitem")) or root

    link = as_tag(fat.select_one(".titleline a"))
    if link is not None:
        story.title = link.get_text(strip=True) or "Untitled"
        story.target_url = attr_str(link, "href")
    site = as_tag(fat.select_one(".sitestr"))
    if site is not None:
        story.site = site.get_text(strip=True)

    user = as_tag(fat.select_one("a.hnuser"))
    if user is not None:
        story.author = user.get_text(strip=True)
    story.date, story.posted_at = _age_date(as_tag(fat.select_one(".age")))

    score = as_tag(fat.select_one(".score"))
    if score is not None:
        story.points = score.get_text(strip=True)
    for a in fat.find_all("a"):
        text = a.get_text(strip=True)
        if text.endswith("comments") or text == "1 comment":
            story.comment_count = text
            break

    story.text = as_tag(fat.select_one(".toptext"))
    return story


def parse_comments(root: Tag) -> list[HNComment]:
    """Parse the comment tree in document (thread) order."""
    comments: list[HNComment] = []
    for row in root.select("tr.athing.comtr"):
        user = as_tag(row.select_one("a.hnuser"))
        _, posted = _age_date(as_tag(row.select_one(".age")))
        ind = as_tag(row.select_one("td.ind"))
        try:
            depth = int(attr_str(ind, "indent") or "0")
        except ValueError:
            depth = 0
        body = as_tag(row.select_one(".commtext"))
        # Dead/flagged comments keep their row but lose .commtext — skip rather
        # than emit an empty attribution block.
        if body is None:
            continue
        comments.append(
            HNComment(
                author=user.get_text(strip=True) if user else None,
                date=posted,
                depth=depth,
                body=body,
            )
        )
    return comments


def _attribution(soup: BeautifulSoup, author: str | None, date: str | None, extra: str = "") -> Tag:
    """A `**author** — date · extra` attribution line."""
    p = soup.new_tag("p")
    strong = soup.new_tag("strong")
    strong.string = author or "unknown"
    p.append(strong)
    tail = " — " + (date or "undated")
    if extra:
        tail += f" · {extra}"
    p.append(soup.new_string(tail))
    return p


def render_story(story: HNStory, full_thread: bool) -> Tag:
    """Rebuild the thread as attributed blocks: submission first, then comments.

    Nested blockquotes carry reply depth, which is the only structure markdownify
    preserves — HN's indent pixels do not survive the HTML→Markdown trip.
    """
    soup = BeautifulSoup("<div></div>", "html.parser")
    root = as_tag(soup.find("div"))
    assert root is not None  # just constructed above

    if story.target_url:
        head = soup.new_tag("p")
        link = soup.new_tag("a", href=story.target_url)
        link.string = story.title
        head.append(link)
        if story.site:
            head.append(soup.new_string(f" ({story.site})"))
        root.append(head)

    meta_bits = " · ".join(b for b in (story.points, story.comment_count) if b)
    root.append(_attribution(soup, story.author, story.posted_at, meta_bits))

    if story.text is not None:
        quote = soup.new_tag("blockquote")
        quote.append(story.text.extract())
        root.append(quote)

    if not full_thread:
        return root

    for c in story.comments:
        root.append(_attribution(soup, c.author, c.date))
        quote = soup.new_tag("blockquote")
        inner = quote
        # depth 0 is a top-level reply; each extra level adds one quote wrapper.
        for _ in range(min(c.depth, 8)):
            deeper = soup.new_tag("blockquote")
            inner.append(deeper)
            inner = deeper
        if c.body is not None:
            inner.append(c.body.extract())
        root.append(quote)
    return root


class HackerNewsAdapter(PlatformAdapter):
    """Hacker News item pages. No <article>/<main> — the whole #hnmain table is
    the content root, rebuilt into attributed submission/comment blocks."""

    name: ClassVar[str] = "hackernews"
    content: ClassVar[Selector | list[Selector]] = [("table", {"id": "hnmain"}), ("body", {})]
    kind: ClassVar[str] = "thread"
    is_thread: ClassVar[bool] = True
    thread_shot_selector: ClassVar[str | None] = "table.fatitem"

    def detect(self, soup: BeautifulSoup) -> bool:
        """True for an HN item page.

        #hnmain is HN's outer table on every page; pairing it with a submission
        row keeps front-page/listing captures from matching an item page's shape.
        """
        if soup.find(id="hnmain") is None:
            return False
        return bool(soup.select_one(".fatitem") or soup.select_one("tr.athing .titleline"))

    def extract_metadata(self, soup: BeautifulSoup) -> PostMetadata:
        """Submission title/date/author, plus the HN category as a tag.

        The description names the outbound target rather than quoting the
        self-text: for a Show HN the thing being cited is the linked project.
        """
        story = parse_story(soup)
        tags = ["hacker news"]
        prefix = _HN_PREFIX_RE.match(story.title)
        if prefix:
            tags.append(f"{prefix.group(1).lower()} hn")

        description = ""
        if story.site:
            description = f"Hacker News discussion of {story.site}"
        elif story.author:
            description = f"Hacker News submission by {story.author}"

        return PostMetadata(
            title=story.title,
            date=story.date,
            description=description,
            tags=tags,
        )

    def clean(self, article: Tag) -> Tag:
        """Non-thread entry point — HN always renders through render_thread()."""
        return article

    def render_thread(self, article: Tag, url: str, base_dir: str | None, full_thread: bool) -> Tag:
        """Submission-only by default; --full-thread appends the comment tree.

        Unlike a paginated forum this needs no crawl: HN serves a thread's
        comments on the item page itself.
        """
        story = parse_story(article)
        if full_thread:
            story.comments = parse_comments(article)
        return render_story(story, full_thread)
