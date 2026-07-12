"""
Capture tier: not every source is convertible HTML. A URL whose content is a PDF,
image, zip, etc. is captured verbatim — saved as an asset and recorded with a
reference — rather than forced through the article pipeline or dropped.
Completeness over cleanliness: every source ends converted, captured, or failed
(never silent).
"""

import os
from urllib.parse import urlparse

from slugify import slugify

from ..config import OUTPUT_DIR
from ..models import Outcome, PostMetadata
from ..network.wayback import unwrap_wayback
from ..targets import OutputTarget

MARKUP_TYPES = ("text/html", "application/xhtml", "application/xml", "text/xml")


def is_markup(content_type: str | None) -> bool:
    """True if a Content-Type should go through the HTML pipeline."""
    ct = (content_type or "").split(";")[0].strip().lower()
    return (not ct) or ct.startswith(MARKUP_TYPES) or ct.endswith("+xml")


def _capture_kind(content_type: str | None) -> str:
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if "pdf" in ct or ct.startswith(("application/msword", "application/vnd")):
        return "document"
    return "file"


def capture_binary(
    content: bytes, content_type: str | None, url: str, tgt: OutputTarget
) -> Outcome:
    """Preserve a non-HTML source verbatim.

    Saves the bytes as an asset and emits a record that references them.

    Args:
        content: The response body.
        content_type: The response's Content-Type header (drives the kind).
        url: The source URL (unwrapped for naming/provenance).
        tgt: The active output target.

    Returns:
        A "captured" Outcome (or "skipped" when the record already exists).
    """
    original = unwrap_wayback(url)
    name = os.path.basename(urlparse(original).path) or "capture"
    slug = slugify(os.path.splitext(name)[0]) or "capture"
    kind = _capture_kind(content_type)

    asset_dir = os.path.join(OUTPUT_DIR, tgt.asset_dir(slug))
    os.makedirs(asset_dir, exist_ok=True)
    with open(os.path.join(asset_dir, name), "wb") as f:
        f.write(content)
    asset_url = tgt.asset_url(slug, name)

    body = f"![{name}]({asset_url})\n" if kind == "image" else f"[{name}]({asset_url})\n"
    meta = PostMetadata(title=name, description=f"Captured {kind}: {name}")
    doc_relpath = tgt.doc_relpath(slug, None)
    if os.path.exists(os.path.join(OUTPUT_DIR, doc_relpath)):
        print(f"  ↷ Already exists, skipping: {doc_relpath}")
        return Outcome("skipped", doc_relpath, reason="exists")
    written = tgt.write(doc_relpath, url, None, "capture", slug, meta, body, "", kind=kind)
    print(f"  ✓ Captured ({kind}): {written}")
    return Outcome("captured", written, reason=kind)
