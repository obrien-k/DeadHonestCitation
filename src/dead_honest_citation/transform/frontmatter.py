"""Lightweight YAML-front-matter lifting for the Markdown passthrough lane."""

import re

FM_BLOCK_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def parse_simple_front_matter(text):
    """Split a leading YAML front-matter block from a Markdown file, lifting
    title/date/description/tags without a YAML dependency. Returns (meta, body)."""
    m = FM_BLOCK_RE.match(text)
    if not m:
        return {}, text
    block, body = m.group(1), text[m.end() :]
    meta = {}
    mt = re.search(r'^title:\s*["\']?(.*?)["\']?\s*$', block, re.M)
    if mt:
        meta["title"] = mt.group(1)
    dt = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})", block, re.M)
    if dt:
        meta["date"] = dt.group(1)
    de = re.search(r'^description:\s*["\']?(.*?)["\']?\s*$', block, re.M)
    if de:
        meta["description"] = de.group(1)
    if "tags:" in block:
        tags = re.findall(r"^\s*-\s*(.+?)\s*$", block[block.index("tags:") :], re.M)
        if tags:
            meta["tags"] = tags
    return meta, body


def first_markdown_heading(body):
    m = re.search(r"^#{1,6}\s+(.+?)\s*$", body, re.M)
    return m.group(1).strip() if m else None
