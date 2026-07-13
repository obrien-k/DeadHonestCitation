"""Shared fixtures: output isolation and offline fixture-page loading."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from dead_honest_citation.network import polite as polite_mod

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate OUTPUT_DIR (a relative "output" path) by chdir'ing into a fresh dir."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _fast_polite_session() -> Iterator[None]:
    """Zero the shared PoliteSession's throttle so mocked-HTTP tests stay fast.

    The whole suite shares one process-wide `_session` (by design — one throttle
    clock per process), so without this every test hitting `polite_get` would pay
    up to DHC_MIN_INTERVAL (default 0.5s) of real sleep. Tests that specifically
    exercise the throttle/retry policy (test_network.py) override this further.
    """
    original = polite_mod._session.min_interval
    polite_mod._session.min_interval = 0
    yield
    polite_mod._session.min_interval = original


@pytest.fixture
def fixture_soup() -> Callable[[str], BeautifulSoup]:
    """Factory: parsed BeautifulSoup for a tests/fixtures/<name> file."""

    def _load(name: str) -> BeautifulSoup:
        html = (FIXTURES_DIR / name).read_text(encoding="utf-8")
        return BeautifulSoup(html, "html.parser")

    return _load
