"""Shared fixtures: output isolation and offline fixture-page loading."""

import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


# --- A local "live web" for the legitimacy gate + Playwright tests -------------
#
# Real HTTP on 127.0.0.1 (no mocks), so redirects, status codes, and a real browser
# all behave as they would against a publisher. Two hostnames reach the same
# server: 127.0.0.1 (the "site") and localhost (another "site", for off-site
# redirects).

_WP_PAGE = (FIXTURES_DIR / "wp-artbody.html").read_text(encoding="utf-8")
_WP_HOME = (
    "<html><head><title>Example Magazine</title>"
    '<link rel="stylesheet" href="/wp-content/themes/x/style.css"></head>'
    "<body><main><article><p>Front page.</p></article></main></body></html>"
)
_SOFT_404 = (
    "<html><head><title>Page not found &#8211; Example Magazine</title>"
    '<link rel="stylesheet" href="/wp-content/themes/x/style.css"></head>'
    "<body><main><article><h1>Oops! That page can&rsquo;t be found.</h1>"
    "<p>Try a search.</p></article></main></body></html>"
)
_PARKED = (
    "<html><head><title>example-magazine.test</title></head><body><main>"
    "<p>This domain is for sale. Inquire today.</p>"
    '<script src="https://www.sedoparking.com/frmpark/x.js"></script></main></body></html>'
)
_PLAIN = (
    "<html><head><title>Hand Rolled</title></head>"
    "<body><main><p>No CMS markers here at all.</p></main></body></html>"
)


class LiveSite:
    """Base URLs of the local site: `url` on 127.0.0.1, `other` on localhost."""

    def __init__(self, port: int) -> None:
        self.url = f"http://127.0.0.1:{port}"
        self.other = f"http://localhost:{port}"


def _make_handler(site: LiveSite) -> type[BaseHTTPRequestHandler]:
    article = "/2009/03/signal-over-noise/"
    routes: dict[str, tuple[int, str | None, str]] = {
        article: (200, None, _WP_PAGE),
        "/": (200, None, _WP_HOME),
        "/old-link": (301, article, ""),
        "/moved": (301, "/", ""),
        "/gone": (404, None, "<html><body><h1>Not Found</h1></body></html>"),
        "/soft404": (200, None, _SOFT_404),
        "/parked": (200, None, _PARKED),
        "/plain": (200, None, _PLAIN),
        "/offsite": (301, f"{site.other}{article}", ""),
        "/chain": (301, "/c1", ""),
        "/c1": (301, "/c2", ""),
        "/c2": (301, "/c3", ""),
        "/c3": (301, "/c4", ""),
        "/c4": (301, article, ""),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            status, location, body = routes.get(
                self.path, (404, None, "<html><body>Not Found</body></html>")
            )
            data = body.encode("utf-8")
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:  # silence test output
            pass

    return Handler


@pytest.fixture(scope="session")
def live_site() -> Iterator[LiveSite]:
    """A threaded local HTTP server playing a publisher's live site."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    site = LiveSite(server.server_address[1])
    server.RequestHandlerClass = _make_handler(site)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield site
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def chromium() -> None:
    """Skip unless Playwright and a launchable Chromium are installed (`.[screenshot]`
    plus `playwright install chromium`)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed (pip install -e '.[screenshot]')")
    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
    except Exception as e:  # browser binary missing / mismatched build
        pytest.skip(f"chromium not launchable: {str(e).splitlines()[0]}")
