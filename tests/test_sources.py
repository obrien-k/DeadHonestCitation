"""core/sources.py: resolving CLI source tokens into a flat work list."""

from pathlib import Path

import pytest

from dead_honest_citation.core import sources as sources_mod
from dead_honest_citation.core.sources import collect_sources

# --- URL passthrough ---------------------------------------------------------


def test_collect_sources_url_passthrough() -> None:
    urls = ["https://example.com/a", "http://example.com/b"]
    assert collect_sources(urls) == urls


# --- directory expansion, *_files pruned ------------------------------------


def test_collect_sources_directory_non_recursive(tmp_path: Path) -> None:
    (tmp_path / "b.html").write_text("<html></html>")
    (tmp_path / "a.htm").write_text("<html></html>")
    (tmp_path / "note.md").write_text("# hi")
    (tmp_path / "ignored.txt").write_text("not a source unless it's the token itself")
    sub = tmp_path / "a_files"
    sub.mkdir()
    (sub / "asset.html").write_text("<html></html>")  # must not surface from a *_files dir

    result = collect_sources([str(tmp_path)])
    assert result == [
        str(tmp_path / "a.htm"),
        str(tmp_path / "b.html"),
        str(tmp_path / "note.md"),
    ]


def test_collect_sources_directory_recursive_prunes_files_dirs(tmp_path: Path) -> None:
    (tmp_path / "real.html").write_text("<html></html>")
    files_dir = tmp_path / "real_files"
    files_dir.mkdir()
    (files_dir / "junk.html").write_text("<html></html>")  # sibling asset dir — pruned
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.html").write_text("<html></html>")

    result = collect_sources([str(tmp_path)], recursive=True)
    assert str(tmp_path / "real.html") in result
    assert str(sub / "nested.html") in result
    assert not any("real_files" in r for r in result)


def test_collect_sources_empty_directory_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    warnings = []
    monkeypatch.setattr(sources_mod, "warn", lambda msg: warnings.append(msg))
    empty = tmp_path / "empty"
    empty.mkdir()
    result = collect_sources([str(empty)])
    assert result == []
    assert any("no source files" in w for w in warnings)


# --- list-file parsing: # comments, blanks ----------------------------------


def test_collect_sources_list_file_comments_and_blanks(tmp_path: Path) -> None:
    list_file = tmp_path / "urls.txt"
    list_file.write_text(
        "\n".join(
            [
                "# a leading comment",
                "https://example.com/one",
                "",
                "  ",
                "   # indented comment",
                "https://example.com/two",
            ]
        )
    )
    result = collect_sources([str(list_file)])
    assert result == ["https://example.com/one", "https://example.com/two"]


# --- .txt list vs --txt content mode ----------------------------------------


def test_txt_file_default_is_list_file(tmp_path: Path) -> None:
    txt = tmp_path / "sources.txt"
    txt.write_text("https://example.com/only-line\n")
    result = collect_sources([str(txt)], txt_as_content=False)
    assert result == ["https://example.com/only-line"]


def test_txt_file_with_txt_mode_is_content(tmp_path: Path) -> None:
    txt = tmp_path / "note.txt"
    txt.write_text("Just some loose prose.\n")
    result = collect_sources([str(txt)], txt_as_content=True)
    assert result == [str(txt)]


# --- dedupe order -------------------------------------------------------------


def test_collect_sources_dedupes_preserving_first_seen_order() -> None:
    urls = [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/a",
        "https://example.com/c",
        "https://example.com/b",
    ]
    assert collect_sources(urls) == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]


# --- missing-file warnings -----------------------------------------------------


def test_collect_sources_missing_file_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings = []
    monkeypatch.setattr(sources_mod, "warn", lambda msg: warnings.append(msg))
    result = collect_sources(["/no/such/path/on/disk.html"])
    assert result == []
    assert any("not found" in w for w in warnings)


def test_collect_sources_missing_non_content_token_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings = []
    monkeypatch.setattr(sources_mod, "warn", lambda msg: warnings.append(msg))
    result = collect_sources(["totally-nonexistent-token"])
    assert result == []
    assert any("not found" in w for w in warnings)
