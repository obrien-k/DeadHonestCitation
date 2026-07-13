"""Output targets: front matter, doc_relpath, and the data target's emit_citation."""

import datetime as dt
from pathlib import Path

from dead_honest_citation.models import Citation, PostMetadata
from dead_honest_citation.targets.commonmark import CommonMarkTarget
from dead_honest_citation.targets.data import emit_citation
from dead_honest_citation.targets.jekyll import JekyllTarget

META = PostMetadata(
    title="Ten Years of Broken Links",
    date=dt.date(2018, 3, 8),
    description="Half the links point at parked domains.",
    tags=["Linkrot", "Preservation"],
    cover="/assets/img/blog/posts/ten-years-of-broken-links/cover.jpg",
    categories=["Essays"],
)


# --- jekyll front matter golden string ---------------------------------------


def test_jekyll_front_matter_golden() -> None:
    target = JekyllTarget()
    fm = target.front_matter(META)
    assert fm == (
        "---\n"
        "layout: post\n"
        'title: "Ten Years of Broken Links"\n'
        "date: 2018-03-08 00:00:00 +0000\n"
        'description: "Half the links point at parked domains."\n'
        "image:\n"
        "  path: /assets/img/blog/posts/ten-years-of-broken-links/cover.jpg\n"
        "tags:\n"
        "  - linkrot\n"
        "  - preservation\n"
        "categories:\n"
        "  - essays\n"
        "---\n\n"
    )


def test_jekyll_front_matter_falls_back_to_first_tag_as_category() -> None:
    meta = PostMetadata(title="No Explicit Category", tags=["Forums"])
    fm = JekyllTarget().front_matter(meta)
    assert "categories:\n  - forums\n" in fm


def test_jekyll_front_matter_escapes_quotes() -> None:
    meta = PostMetadata(title='A "Quoted" Title')
    fm = JekyllTarget().front_matter(meta)
    assert 'title: "A \\"Quoted\\" Title"' in fm


# --- commonmark front matter golden string -----------------------------------


def test_commonmark_front_matter_golden() -> None:
    target = CommonMarkTarget()
    fm = target.front_matter(META)
    assert fm == (
        "---\n"
        'title: "Ten Years of Broken Links"\n'
        "date: 2018-03-08\n"
        'description: "Half the links point at parked domains."\n'
        "tags:\n"
        "  - linkrot\n"
        "  - preservation\n"
        "---\n\n"
    )


# --- doc_relpath date handling ------------------------------------------------


def test_jekyll_doc_relpath_with_date() -> None:
    assert (
        JekyllTarget().doc_relpath("my-slug", dt.date(2018, 3, 8)) == "_posts/2018-03-08-my-slug.md"
    )


def test_jekyll_doc_relpath_none_date_falls_back() -> None:
    assert JekyllTarget().doc_relpath("my-slug", None) == "_posts/0000-00-00-my-slug.md"


def test_commonmark_doc_relpath_ignores_date() -> None:
    assert CommonMarkTarget().doc_relpath("my-slug", None) == "my-slug.md"
    assert CommonMarkTarget().doc_relpath("my-slug", dt.date(2018, 3, 8)) == "my-slug.md"


# --- data target: emit_citation writes yml+md+include ------------------------


def test_emit_citation_writes_yml_md_and_include(tmp_output: Path) -> None:
    out_dir = str(tmp_output / "output")
    cite = Citation(
        provenance="archived",
        source_url="https://example.com/post",
        archive_url="https://web.archive.org/web/20190402101500/https://example.com/post",
        captured_at="2019-04-02",
        kind="post",
    )
    meta = PostMetadata(title="How the Archive Remembers")
    relpath = emit_citation(out_dir, "how-the-archive-remembers", meta, "Body text.\n", "", cite)

    assert relpath == "_data/sources/how-the-archive-remembers.yml"
    yml_path = Path(out_dir) / relpath
    assert yml_path.exists()
    yml_text = yml_path.read_text(encoding="utf-8")
    assert "id: how-the-archive-remembers" in yml_text
    assert 'title: "How the Archive Remembers"' in yml_text
    assert "kind: post" in yml_text
    assert "provenance: archived" in yml_text
    assert 'source_url: "https://example.com/post"' in yml_text
    assert "archive_url:" in yml_text
    assert "captured_at: 2019-04-02" in yml_text

    md_path = Path(out_dir) / "_sources" / "how-the-archive-remembers.md"
    assert md_path.read_text(encoding="utf-8") == "Body text.\n"

    include_path = Path(out_dir) / "_includes" / "cite.html"
    assert include_path.exists()
    assert "site.data.sources" in include_path.read_text(encoding="utf-8")


def test_emit_citation_note_and_screenshot_fields(tmp_output: Path) -> None:
    out_dir = str(tmp_output / "output")
    cite = Citation(
        provenance="local",
        source_url="thread.html",
        archive_url=None,
        captured_at=None,
        kind="thread",
    )
    meta = PostMetadata(
        title="A Forum Thread",
        screenshot="/assets/img/sources/a-forum-thread/a-forum-thread-cover.png",
        screenshot_note="Banner-to-first-post capture of the original forum thread.",
    )
    relpath = emit_citation(out_dir, "a-forum-thread", meta, "Body.\n", "", cite)
    yml_text = (Path(out_dir) / relpath).read_text(encoding="utf-8")
    assert "screenshot: " in yml_text
    assert "a-forum-thread-cover.png" in yml_text
    assert 'note: "Banner-to-first-post capture of the original forum thread."' in yml_text


def test_emit_citation_ensure_cite_include_written_once(tmp_output: Path) -> None:
    out_dir = str(tmp_output / "output")
    cite = Citation(
        provenance="live",
        source_url="https://example.com",
        archive_url=None,
        captured_at="2026-01-01",
        kind="page",
    )
    meta = PostMetadata(title="One")
    emit_citation(out_dir, "one", meta, "Body.\n", "", cite)
    include_path = Path(out_dir) / "_includes" / "cite.html"
    first_mtime = include_path.stat().st_mtime_ns
    emit_citation(out_dir, "two", meta, "Body.\n", "", cite)
    assert include_path.stat().st_mtime_ns == first_mtime
