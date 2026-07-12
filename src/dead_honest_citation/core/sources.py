"""
The input layer: resolve CLI source tokens into a flat work list and load each
source's raw content. This is the input-agnostic seam — the adapter registry is
untouched; this layer only decides *what to feed* the per-source pipeline.
"""

import os
from collections.abc import Iterable

from ..adapters.docx import docx_to_html
from ..network.polite import polite_get

# Local file extensions the pipeline can read directly (a saved page or a Word doc).
SOURCE_EXTS = (".html", ".htm", ".docx")

# Loose Markdown files are already in the output format and skip the HTML round-trip.
MD_EXTS = (".md", ".markdown")


def is_local_source(src: str) -> bool:
    """True if src is a local HTML file to read rather than a URL to fetch."""
    if src.startswith(("http://", "https://")):
        return False
    return src.lower().endswith(SOURCE_EXTS) or os.path.exists(os.path.expanduser(src))


def is_markdown_source(src: str, md_mode: bool = False) -> bool:
    """True if a source should be handled as Markdown/plain-text passthrough."""
    if src.startswith(("http://", "https://")):
        return False
    low = src.lower()
    return low.endswith(MD_EXTS) or (md_mode and low.endswith(".txt"))


def load_source(src: str) -> tuple[str, str | None]:
    """Load a source's raw HTML.

    Args:
        src: A local file path or an http(s) URL.

    Returns:
        (html_text, base_dir). For a local file, base_dir is its directory,
        used to resolve the sibling "<name>_files/" asset folder; for a URL,
        base_dir is None and the page is fetched over the network.
    """
    if is_local_source(src):
        path = os.path.expanduser(src)
        if path.lower().endswith(".docx"):
            return docx_to_html(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(), os.path.dirname(os.path.abspath(path))
    return polite_get(src).text, None


def _dir_sources(directory: str, recursive: bool, exts: tuple[str, ...] = SOURCE_EXTS) -> list[str]:
    """Every source file (matching exts) inside a directory, sorted.

    Saved-page asset folders ('<name>_files/') and dotfiles are skipped — they hold
    images, not pages. With recursive, walk subdirectories too (still pruning any
    '*_files' tree and hidden dirs)."""
    found = []
    if recursive:
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.endswith("_files") and not d.startswith(".")]
            for name in files:
                if name.lower().endswith(exts) and not name.startswith("."):
                    found.append(os.path.join(root, name))
    else:
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if not name.startswith(".") and os.path.isfile(path) and name.lower().endswith(exts):
                found.append(path)
    return sorted(found)


def collect_sources(
    tokens: Iterable[str], recursive: bool = False, txt_as_content: bool = False
) -> list[str]:
    """Resolve CLI source tokens into a flat, de-duplicated work list.

    Each token is classified independently, so one run can mix input kinds:
      - a directory            → every source file inside (recursive opt-in)
      - a URL (http/https)     → itself
      - a content file         → itself (.html/.htm/.docx page or Word doc, .md/
                                  .markdown, and .txt when txt_as_content)
      - any other existing file → a *list file*: read it, one source per non-blank,
                                  non-'#' line (the classic urls.txt — .txt stays a
                                  list file unless txt_as_content)
      - anything else          → reported missing and skipped

    Args:
        tokens: The positional CLI source arguments.
        recursive: Recurse into subdirectories of directory tokens.
        txt_as_content: Treat .txt files as passthrough content, not list files.

    Returns:
        The de-duplicated sources in first-seen order.
    """
    content_exts = SOURCE_EXTS + MD_EXTS + ((".txt",) if txt_as_content else ())
    sources = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        expanded = os.path.expanduser(token)
        if os.path.isdir(expanded):
            hits = _dir_sources(expanded, recursive, content_exts)
            if not hits:
                print(f"  ⚠ no source files in directory: {token}")
            sources.extend(hits)
        elif token.startswith(("http://", "https://")):
            sources.append(token)
        elif token.lower().endswith(content_exts):
            # A non-URL content token is a local page/doc/markdown file; it must exist.
            if os.path.isfile(expanded):
                sources.append(expanded)
            else:
                print(f"  ⚠ source not found, skipping: {token}")
        elif os.path.isfile(expanded):
            with open(expanded, encoding="utf-8", errors="replace") as f:
                sources.extend(
                    ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")
                )
        else:
            print(f"  ⚠ source not found, skipping: {token}")
    # De-duplicate while preserving first-seen order.
    seen, unique = set(), []
    for s in sources:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique
