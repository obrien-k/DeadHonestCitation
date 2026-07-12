"""The commonmark output target: flat, SSG-neutral Markdown files."""

import os

from slugify import slugify

from .base import escape_table_pipes


def commonmark_front_matter(meta):
    """Minimal, SSG-neutral YAML front matter (no Jekyll-specific keys)."""
    safe_title = meta["title"].replace('"', '\\"')
    lines = ["---", f'title: "{safe_title}"']
    if meta.get("date"):
        lines.append(f"date: {meta['date']}")
    if meta.get("description"):
        safe_desc = meta["description"].replace('"', '\\"')
        lines.append(f'description: "{safe_desc}"')
    if meta.get("tags"):
        lines.append("tags:")
        for t in meta["tags"]:
            lines.append(f"  - {slugify(t)}")
    lines.append("---\n")
    return "\n".join(lines) + "\n"


TARGET = {
    "doc_relpath": lambda slug, date: f"{slug}.md",
    "asset_dir": lambda slug: os.path.join("assets", slug),
    "asset_url": lambda slug, fname: f"assets/{slug}/{fname}",
    "front_matter": commonmark_front_matter,
    "flavor": escape_table_pipes,
}
