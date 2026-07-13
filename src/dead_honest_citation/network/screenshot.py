"""Page-to-PNG rendering for citation evidence (lazy, optional playwright)."""

from ..ui import warn


def screenshot_page(
    url: str, out_path: str, end_selector: str | None = None, timeout: float = 30000
) -> bool:
    """Render a page to a PNG with a headless browser.

    With end_selector, crop from the top of the page (the banner) down to the
    bottom of the first matching element — the banner→first-post cover for a
    forum thread; without it, a full-page shot. Playwright is imported lazily
    and optional — like mammoth for .docx — so the core install stays light; it
    no-ops with a hint when absent.

    Args:
        url: The page (or local path) to render.
        out_path: Destination PNG path.
        end_selector: CSS selector whose first match sets the crop's bottom edge.
        timeout: Navigation timeout in milliseconds.

    Returns:
        True on success.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        warn(
            "  ⚠ screenshots need playwright: pip install playwright && playwright install chromium"
        )
        return False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1024, "height": 1400})
            page.goto(url, wait_until="networkidle", timeout=timeout)
            clip = None
            if end_selector:
                el = page.query_selector(end_selector)
                box = el.bounding_box() if el else None
                if box:
                    width = page.evaluate("document.documentElement.scrollWidth")
                    clip = {
                        "x": 0.0,
                        "y": 0.0,
                        "width": min(float(width), 1024.0),
                        "height": box["y"] + box["height"],
                    }
                else:
                    warn("  ⚠ screenshot: first-post element not found, using full page")
            if clip:
                page.screenshot(path=out_path, clip=clip)
            else:
                page.screenshot(path=out_path, full_page=True)
            browser.close()
        return True
    except Exception as e:
        warn(f"  ⚠ screenshot failed: {e}")
        return False
