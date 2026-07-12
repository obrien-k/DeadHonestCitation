"""
Output targets: how a converted source is written — front-matter format, file
naming/layout, asset paths, and Markdown-flavor tweaks. The conversion core stays
target-agnostic (it produces metadata + body + assets), so supporting another
static-site generator means adding one TARGETS entry. Each supplies:
  doc_relpath(slug, date) → path (under OUTPUT_DIR) for the document file
  asset_dir(slug)         → dir  (under OUTPUT_DIR) holding that post's images
  asset_url(slug, fname)  → the in-document URL for a localized image
  front_matter(meta)      → the front-matter block
  flavor(markdown)        → post-process the Markdown body
or an `emit` hook to write something other than a single document.
"""

import os

from ..config import OUTPUT_DIR
from . import commonmark, data, jekyll
from .data import derive_citation

TARGETS = {
    "jekyll": jekyll.TARGET,
    "commonmark": commonmark.TARGET,
    # Provenance-stamped citation records, not posts. Writes _data/sources/<id>.yml
    # + _sources/<id>.md via emit_citation; images go under /assets/img/sources/.
    "data": data.TARGET,
}

TARGET_ALIASES = {
    "jekyll": "jekyll",
    "jk": "jekyll",
    "commonmark": "commonmark",
    "cm": "commonmark",
    "plain": "commonmark",
    "md": "commonmark",
    "data": "data",
    "citation": "data",
    "cite": "data",
}


def resolve_target(name):
    """Map a target name/alias to its TARGETS entry (defaults to jekyll)."""
    return TARGETS[TARGET_ALIASES.get(name or "jekyll", name or "jekyll")]


def emit_source(
    tgt, doc_relpath, url, base_dir, platform_name, slug, meta, body, footnotes, kind=None
):
    """Write one converted source via the active target; return its relpath. Shared by
    the HTML pipeline (process_url), the Markdown passthrough (process_markdown), and
    the capture tier (capture_binary)."""
    if tgt.get("emit"):
        cite = derive_citation(url, base_dir, platform_name, kind=kind)
        return tgt["emit"](OUTPUT_DIR, slug, meta, body, footnotes, cite)
    filepath = os.path.join(OUTPUT_DIR, doc_relpath)
    front_matter = tgt["front_matter"](meta)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(front_matter)
        f.write(body)
        if footnotes.strip():
            f.write(footnotes)
    return doc_relpath
