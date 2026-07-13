"""targets/data.py: derive_citation() — honest provenance by construction."""

import time

from dead_honest_citation.targets.data import derive_citation

# --- wayback URL -> archived, with timestamp parse ---------------------------


def test_derive_citation_wayback_url_is_archived() -> None:
    url = "https://web.archive.org/web/20190402101500/https://example.com/post"
    cite = derive_citation(url, base_dir=None, platform_name="ghost")
    assert cite.provenance == "archived"
    assert cite.source_url == "https://example.com/post"
    assert cite.archive_url == url
    assert cite.captured_at == "2019-04-02"
    assert cite.kind == "post"


def test_derive_citation_wayback_url_with_capture_suffix_is_archived() -> None:
    url = "https://web.archive.org/web/20190402101500im_/https://example.com/img.png"
    cite = derive_citation(url, base_dir=None, platform_name="generic")
    assert cite.provenance == "archived"
    assert cite.source_url == "https://example.com/img.png"
    assert cite.captured_at == "2019-04-02"


# --- plain URL -> live, access date = today ----------------------------------


def test_derive_citation_plain_url_is_live_with_todays_access_date() -> None:
    cite = derive_citation("https://example.com/post", base_dir=None, platform_name="wordpress")
    assert cite.provenance == "live"
    assert cite.source_url == "https://example.com/post"
    assert cite.archive_url is None
    assert cite.captured_at == time.strftime("%Y-%m-%d")
    assert cite.kind == "post"


# --- base_dir set -> local, basename only, no archive_url --------------------


def test_derive_citation_local_source_uses_basename_only() -> None:
    cite = derive_citation(
        "/Users/kai/saved-pages/wp-post.html",
        base_dir="/Users/kai/saved-pages",
        platform_name="wordpress",
    )
    assert cite.provenance == "local"
    assert cite.source_url == "wp-post.html"
    assert cite.archive_url is None
    assert cite.captured_at is None
    assert cite.kind == "post"


# --- kind mapping + override --------------------------------------------------


def test_derive_citation_kind_from_platform_map() -> None:
    assert derive_citation("https://example.com", None, "ghost").kind == "post"
    assert derive_citation("https://example.com", None, "wordpress").kind == "post"
    assert derive_citation("https://example.com", None, "generic").kind == "page"
    assert derive_citation("https://example.com", None, "docx").kind == "document"
    assert derive_citation("https://example.com", None, "proboards").kind == "thread"
    assert derive_citation("https://example.com", None, "txt").kind == "document"
    # Unknown platform names default to "page".
    assert derive_citation("https://example.com", None, "unknown-platform").kind == "page"


def test_derive_citation_kind_override_wins() -> None:
    cite = derive_citation("https://example.com/image.png", None, "capture", kind="image")
    assert cite.kind == "image"
