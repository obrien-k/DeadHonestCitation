"""network/wayback.py: snapshot URL math + CDX/Save-Page-Now discovery (mocked HTTP)."""

import responses

from dead_honest_citation.network.wayback import (
    CDX_API,
    SAVE_API,
    discover,
    save_page_now,
    unwrap_wayback,
    wayback_image_candidates,
    wayback_raw,
)

# --- unwrap_wayback, including im_/if_ suffixes ------------------------------


def test_unwrap_wayback_plain_capture() -> None:
    url = "https://web.archive.org/web/20190402101500/https://example.com/post"
    assert unwrap_wayback(url) == "https://example.com/post"


def test_unwrap_wayback_im_suffix() -> None:
    url = "https://web.archive.org/web/20190402101500im_/https://example.com/img.png"
    assert unwrap_wayback(url) == "https://example.com/img.png"


def test_unwrap_wayback_if_suffix() -> None:
    url = "https://web.archive.org/web/20190402101500if_/https://example.com/thread"
    assert unwrap_wayback(url) == "https://example.com/thread"


def test_unwrap_wayback_non_wayback_url_passes_through() -> None:
    assert unwrap_wayback("https://example.com/post") == "https://example.com/post"


def test_unwrap_wayback_relative_web_path() -> None:
    url = "/web/20190402101500/https://example.com/post"
    assert unwrap_wayback(url) == "https://example.com/post"


# --- wayback_image_candidates -------------------------------------------------


def test_wayback_image_candidates_timestamped() -> None:
    src = "https://web.archive.org/web/20190402101500/https://example.com/img.png"
    candidates = wayback_image_candidates(src)
    assert candidates == [
        "https://web.archive.org/web/20190402101500im_/https://example.com/img.png",
        "https://example.com/img.png",
    ]


def test_wayback_image_candidates_relative_web_path() -> None:
    src = "/web/20190402101500/https://example.com/img.png"
    candidates = wayback_image_candidates(src)
    assert candidates[0].startswith("https://web.archive.org/web/20190402101500im_/")


def test_wayback_image_candidates_non_wayback_src_passes_through() -> None:
    assert wayback_image_candidates("https://cdn.example.com/img.png") == [
        "https://cdn.example.com/img.png"
    ]


# --- wayback_raw ---------------------------------------------------------------


def test_wayback_raw_inserts_if_suffix() -> None:
    url = "https://web.archive.org/web/20190402101500/https://example.com/thread"
    assert (
        wayback_raw(url)
        == "https://web.archive.org/web/20190402101500if_/https://example.com/thread"
    )


def test_wayback_raw_non_wayback_url_passes_through() -> None:
    assert wayback_raw("https://example.com/thread") == "https://example.com/thread"


# --- discover(): CDX parsing via responses, incl. &amp; decode ---------------


@responses.activate
def test_discover_parses_cdx_rows_and_decodes_amp() -> None:
    body = (
        "20190101000000 https://example.com/thread?board=1&amp;topic=2\n"
        "20190202000000 https://example.com/other\n"
    )
    responses.add(responses.GET, CDX_API, body=body, status=200)
    rows = discover("example.com")
    assert rows == [
        ("20190101000000", "https://example.com/thread?board=1&topic=2"),
        ("20190202000000", "https://example.com/other"),
    ]


@responses.activate
def test_discover_skips_blank_lines() -> None:
    body = "20190101000000 https://example.com/thread\n\n   \n"
    responses.add(responses.GET, CDX_API, body=body, status=200)
    rows = discover("example.com")
    assert rows == [("20190101000000", "https://example.com/thread")]


@responses.activate
def test_discover_empty_response() -> None:
    responses.add(responses.GET, CDX_API, body="", status=200)
    assert discover("example.com") == []


# --- save_page_now(): Content-Location -----------------------------------------


@responses.activate
def test_save_page_now_returns_permalink_from_content_location() -> None:
    target = "https://example.com/some-page"
    responses.add(
        responses.GET,
        SAVE_API + target,
        status=200,
        headers={"Content-Location": "/web/20240101000000/https://example.com/some-page"},
    )
    result = save_page_now(target)
    assert result == "https://web.archive.org/web/20240101000000/https://example.com/some-page"


@responses.activate
def test_save_page_now_prepends_https_when_scheme_missing() -> None:
    responses.add(
        responses.GET,
        SAVE_API + "https://example.com/bare",
        status=200,
        headers={"Content-Location": "/web/20240101000000/https://example.com/bare"},
    )
    result = save_page_now("example.com/bare")
    assert result == "https://web.archive.org/web/20240101000000/https://example.com/bare"


@responses.activate
def test_save_page_now_returns_none_without_snapshot() -> None:
    target = "https://example.com/no-snapshot"
    responses.add(responses.GET, SAVE_API + target, status=200, body="ok")
    result = save_page_now(target)
    assert result is None
