"""Per-platform adapter tests: detection and metadata/body extraction, offline."""

import datetime as dt
from collections.abc import Callable
from pathlib import Path

from bs4 import BeautifulSoup

from dead_honest_citation.adapters import PLATFORMS, detect_platform
from dead_honest_citation.adapters.docx import docx_to_html
from dead_honest_citation.adapters.generic import GenericAdapter, extract_metadata_generic
from dead_honest_citation.adapters.proboards import proboards_render

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --- detect_platform() picks the right adapter -----------------------------


def test_detect_platform_ghost(fixture_soup: Callable[[str], BeautifulSoup]) -> None:
    soup = fixture_soup("ghost-post.html")
    assert detect_platform(soup) == "ghost"


def test_detect_platform_wordpress(fixture_soup: Callable[[str], BeautifulSoup]) -> None:
    soup = fixture_soup("wp-post.html")
    assert detect_platform(soup) == "wordpress"


def test_detect_platform_proboards(fixture_soup: Callable[[str], BeautifulSoup]) -> None:
    soup = fixture_soup("pb-thread.html")
    assert detect_platform(soup) == "proboards"


def test_detect_platform_docx(fixture_soup: Callable[[str], BeautifulSoup]) -> None:
    html, _base_dir = docx_to_html(str(FIXTURES_DIR / "field-notes.docx"))
    soup = BeautifulSoup(html, "html.parser")
    assert detect_platform(soup) == "docx"


def test_generic_never_auto_detects() -> None:
    # detect() is always False so --html/--platform generic must be forced.
    assert (
        GenericAdapter().detect(BeautifulSoup("<article><h1>x</h1></article>", "html.parser"))
        is False
    )


def test_detect_platform_none_for_unrecognized_markup() -> None:
    soup = BeautifulSoup("<html><body><p>just a paragraph</p></body></html>", "html.parser")
    assert detect_platform(soup) is None


# --- Ghost: title/date/tags/description -------------------------------------


def test_ghost_extract_metadata(fixture_soup: Callable[[str], BeautifulSoup]) -> None:
    soup = fixture_soup("ghost-post.html")
    meta = PLATFORMS["ghost"].extract_metadata(soup)
    assert meta.title == "How the Archive Remembers"
    assert meta.date == dt.date(2019, 4, 2)
    assert meta.tags == ["archives", "web history"]
    assert meta.description == "A short field guide to reading dead websites."


def test_ghost_clean_normalizes_second_h1() -> None:
    # normalize_headings demotes any h1 after the first — Ghost bodies sometimes
    # repeat an h1 inline, which would otherwise compete with the front-matter title.
    html = '<section class="gh-content"><h1>First</h1><p>x</p><h1>Second</h1></section>'
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("section", class_="gh-content")
    cleaned = PLATFORMS["ghost"].clean(article)
    assert [h.get_text(strip=True) for h in cleaned.find_all("h1")] == ["First"]
    assert cleaned.find("h2").get_text(strip=True) == "Second"


def test_ghost_clean_strips_kg_classes(fixture_soup: Callable[[str], BeautifulSoup]) -> None:
    # clean_ghost_classes scrubs descendant Koenig/Ghost classes (the root
    # selector tag itself is left alone — the pipeline discards it anyway).
    soup = fixture_soup("ghost-post.html")
    article = soup.find("section", class_="gh-content")
    cleaned = PLATFORMS["ghost"].clean(article)
    figure = cleaned.find("figure")
    assert not any(c.startswith(("gh-", "kg-")) for c in (figure.get("class") or []))


# --- WordPress: title/date/tags/categories, cruft removal -------------------


def test_wordpress_extract_metadata(fixture_soup: Callable[[str], BeautifulSoup]) -> None:
    soup = fixture_soup("wp-post.html")
    meta = PLATFORMS["wordpress"].extract_metadata(soup)
    assert meta.title == "Ten Years of Broken Links"
    assert meta.date == dt.date(2018, 3, 8)
    assert meta.tags == ["linkrot", "preservation"]
    assert meta.categories == ["Essays"]


def test_wordpress_clean_removes_cruft(fixture_soup: Callable[[str], BeautifulSoup]) -> None:
    soup = fixture_soup("wp-post.html")
    article = soup.find("div", class_="post-content")
    cleaned = PLATFORMS["wordpress"].clean(article)
    text = cleaned.get_text(" ", strip=True)
    assert "share buttons that should vanish" not in text
    assert "related cards that should vanish" not in text
    assert "Plain text survives" in text


# --- ProBoards: OP-only render, author/date attribution, footer stripped ----


def test_proboards_extract_metadata(fixture_soup: Callable[[str], BeautifulSoup]) -> None:
    soup = fixture_soup("pb-thread.html")
    meta = PLATFORMS["proboards"].extract_metadata(soup)
    assert meta.title == "Anyone still modding the PS2?"
    assert meta.date == dt.date(2005, 3, 14)


def test_proboards_clean_default_is_op_only(fixture_soup: Callable[[str], BeautifulSoup]) -> None:
    soup = fixture_soup("pb-thread.html")
    body = soup.find("body")
    rendered = PLATFORMS["proboards"].clean(body)
    text = rendered.get_text(" ", strip=True)
    assert "solderking" in text
    assert "Mar 14, 2005, 9:12pm" in text
    assert "Picked up a fat PS2" in text
    # OP-only: reply #1 must not appear by default.
    assert "modchip_mary" not in text
    assert "FreeMCBoot" not in text
    # Footer noise (signature line) is stripped from the message.
    assert "Logged" not in text
    assert "signature junk" not in text


def test_proboards_full_thread_keeps_every_post(
    fixture_soup: Callable[[str], BeautifulSoup],
) -> None:
    soup = fixture_soup("pb-thread.html")
    body = soup.find("body")
    rendered = PLATFORMS["proboards"].clean(body, full_thread=True)
    text = rendered.get_text(" ", strip=True)
    assert "solderking" in text
    assert "modchip_mary" in text
    assert "FreeMCBoot" in text


def test_proboards_render_attribution_format() -> None:
    from dead_honest_citation.adapters.proboards import PBPost

    post = PBPost(author="solderking", subject="Subject", date="Mar 14, 2005, 9:12pm", message=None)
    rendered = proboards_render([post])
    head = rendered.find("p")
    assert head.find("strong").get_text(strip=True) == "solderking"
    assert "Mar 14, 2005, 9:12pm" in head.get_text()


# --- docx: core-props title/date via docx_to_html ---------------------------


def test_docx_to_html_core_props() -> None:
    html, base_dir = docx_to_html(str(FIXTURES_DIR / "field-notes.docx"))
    soup = BeautifulSoup(html, "html.parser")
    meta = PLATFORMS["docx"].extract_metadata(soup)
    assert meta.title == "Field Notes on Dead Hyperlinks"
    assert meta.date == dt.date(2021, 2, 3)
    assert base_dir  # a temp dir for extracted embedded images


# --- generic: inline snippet --------------------------------------------------


def test_generic_extract_metadata_inline_snippet() -> None:
    html = """
    <html><head>
      <meta property="og:title" content="An Untitled Page">
      <meta property="og:description" content="No CMS recognized this page.">
    </head><body>
      <article><p>Some body text.</p></article>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    meta = extract_metadata_generic(soup)
    assert meta.title == "An Untitled Page"
    assert meta.description == "No CMS recognized this page."


def test_generic_content_selector_fallback_to_article() -> None:
    html = "<html><body><article><p>Body text here.</p></article></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    selectors = GenericAdapter.content
    article = None
    for name, attrs in selectors:
        found = soup.find(name, attrs)
        if found is not None:
            article = found
            break
    assert article is not None
    assert article.name == "article"
    assert "Body text here." in article.get_text()
