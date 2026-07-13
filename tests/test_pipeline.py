"""End-to-end offline pipeline tests: local HTML + Markdown into jekyll/commonmark."""

import shutil
from pathlib import Path

import pytest

from dead_honest_citation.core.pipeline import process_markdown, process_url

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _copy_sources(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES_DIR / "ghost-post.html", dest / "ghost-post.html")
    shutil.copytree(FIXTURES_DIR / "ghost-post_files", dest / "ghost-post_files")
    shutil.copy(FIXTURES_DIR / "note.md", dest / "note.md")


@pytest.mark.parametrize(
    "target,doc_relpath,asset_relpath",
    [
        (
            "jekyll",
            "_posts/2019-04-02-how-the-archive-remembers.md",
            "assets/img/blog/posts/how-the-archive-remembers/pixel.png",
        ),
        (
            "commonmark",
            "how-the-archive-remembers.md",
            "assets/how-the-archive-remembers/pixel.png",
        ),
    ],
)
def test_convert_ghost_post_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    doc_relpath: str,
    asset_relpath: str,
) -> None:
    src_dir = tmp_path / "src"
    _copy_sources(src_dir)
    monkeypatch.chdir(tmp_path)

    outcome = process_url(str(src_dir / "ghost-post.html"), target=target)
    assert outcome.status == "converted"
    assert outcome.output == doc_relpath

    doc_path = tmp_path / "output" / doc_relpath
    assert doc_path.exists()
    body = doc_path.read_text(encoding="utf-8")

    # Front matter fields.
    assert 'title: "How the Archive Remembers"' in body
    assert "date: 2019-04-02" in body
    assert 'description: "A short field guide to reading dead websites."' in body
    assert "- archives" in body
    assert "- web-history" in body

    # Footnote converted to Markdown [^1] syntax, inline and defined.
    assert "[^1]" in body
    assert "[^1]: Testimony in the archival sense, not the courtroom sense." in body

    # YouTube iframe embed became a labeled Markdown link.
    assert "[▶ Watch on YouTube](https://www.youtube.com/watch?v=dQw4w9WgXcQ)" in body

    # Image copied from the sibling ghost-post_files/ dir and src rewritten.
    asset_path = tmp_path / "output" / asset_relpath
    assert asset_path.exists()
    assert asset_relpath.split("/")[-1] in body  # rewritten <img> src references it


@pytest.mark.parametrize(
    "target,doc_relpath",
    [
        ("jekyll", "_posts/2020-11-05-marginalia-on-a-dead-forum.md"),
        ("commonmark", "marginalia-on-a-dead-forum.md"),
    ],
)
def test_convert_markdown_passthrough_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, doc_relpath: str
) -> None:
    src_dir = tmp_path / "src"
    _copy_sources(src_dir)
    monkeypatch.chdir(tmp_path)

    outcome = process_markdown(str(src_dir / "note.md"), target=target)
    assert outcome.status == "converted"
    assert outcome.output == doc_relpath

    doc_path = tmp_path / "output" / doc_relpath
    assert doc_path.exists()
    body = doc_path.read_text(encoding="utf-8")
    assert 'title: "Marginalia on a Dead Forum"' in body
    assert "date: 2020-11-05" in body
    assert "- forums" in body
    assert "- notes" in body
    # Verbatim body, kept as-is.
    assert "The OP is the citation anchor." in body


def test_reconvert_ghost_post_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src_dir = tmp_path / "src"
    _copy_sources(src_dir)
    monkeypatch.chdir(tmp_path)

    first = process_url(str(src_dir / "ghost-post.html"), target="jekyll")
    assert first.status == "converted"

    second = process_url(str(src_dir / "ghost-post.html"), target="jekyll")
    assert second.status == "skipped"
    assert second.reason == "exists"
    assert second.output == first.output


def test_reconvert_markdown_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src_dir = tmp_path / "src"
    _copy_sources(src_dir)
    monkeypatch.chdir(tmp_path)

    first = process_markdown(str(src_dir / "note.md"), target="jekyll")
    assert first.status == "converted"

    second = process_markdown(str(src_dir / "note.md"), target="jekyll")
    assert second.status == "skipped"
    assert second.reason == "exists"
