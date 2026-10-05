"""Playwright: real-Chromium screen capture, and the live photo-record end to end.

Marked `browser`; skipped unless playwright + a launchable Chromium are installed.
Fast loop without them: pytest -m "not browser".
"""

import shutil
import struct
from pathlib import Path

import pytest
from conftest import LiveSite

from dead_honest_citation.core.pipeline import process_url
from dead_honest_citation.network.screenshot import screenshot_page

pytestmark = [pytest.mark.browser, pytest.mark.usefixtures("chromium")]

ARTICLE = "/2009/03/signal-over-noise/"


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_screenshot_full_page(live_site: LiveSite, tmp_path: Path) -> None:
    out = tmp_path / "full.png"
    assert screenshot_page(f"{live_site.url}{ARTICLE}", str(out))
    width, height = _png_size(out)
    assert width == 1024
    assert height >= 1400  # full page is at least the viewport


def test_screenshot_crops_to_end_selector(live_site: LiveSite, tmp_path: Path) -> None:
    full, cropped = tmp_path / "full.png", tmp_path / "crop.png"
    assert screenshot_page(f"{live_site.url}{ARTICLE}", str(full))
    assert screenshot_page(f"{live_site.url}{ARTICLE}", str(cropped), end_selector=".art-deck")
    assert _png_size(cropped)[1] < _png_size(full)[1]


def test_legitimate_live_copy_gets_a_photo_record(
    live_site: LiveSite, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    outcome = process_url(f"{live_site.url}/old-link", target="data")
    assert outcome.status == "converted"

    yml = (tmp_path / "output/_data/sources/signal-over-noise.yml").read_text("utf-8")
    assert "provenance: live" in yml
    assert 'screenshot: "/assets/img/sources/signal-over-noise/signal-over-noise-live.png"' in yml
    assert "Live capture " in yml
    assert "HTTP 200, 1 redirect(s), CMS: wordpress." in yml
    shot = tmp_path / "output/assets/img/sources/signal-over-noise/signal-over-noise-live.png"
    assert _png_size(shot)[0] == 1024


def test_illegitimate_live_copy_gets_none(
    live_site: LiveSite, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Parked: still converted (the cascade never dead-ends), but no photo-record,
    # even with --screenshot asked for.
    monkeypatch.chdir(tmp_path)
    outcome = process_url(f"{live_site.url}/parked", target="data", screenshot=True)
    assert outcome.status in ("converted", "captured")
    for yml in (tmp_path / "output/_data/sources").glob("*.yml"):
        assert "screenshot:" not in yml.read_text("utf-8")
    assert not list(tmp_path.glob("output/assets/**/*.png"))


def test_archived_source_keeps_the_screenshot_flag(
    live_site: LiveSite, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A local file is not live: the gate doesn't apply and --screenshot behaves as before.
    src = tmp_path / "saved.html"
    shutil.copy(Path(__file__).parent / "fixtures" / "wp-artbody.html", src)
    monkeypatch.chdir(tmp_path)
    outcome = process_url(str(src), target="data", screenshot=True)
    assert outcome.status == "converted"
    yml = (tmp_path / "output/_data/sources/signal-over-noise.yml").read_text("utf-8")
    assert "provenance: local" in yml
    assert "signal-over-noise-screenshot.png" in yml
