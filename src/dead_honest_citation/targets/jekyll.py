"""The jekyll output target: dated _posts/ files with Jekyll front matter."""

import os

from slugify import slugify

from .base import escape_table_pipes


def build_front_matter(meta):
    """Jekyll-compatible YAML front matter from a metadata dict."""
    title = meta["title"]
    date = meta.get("date")
    description = meta.get("description")
    tags = meta.get("tags") or []
    cover = meta.get("cover")
    categories = meta.get("categories")
    safe_title = title.replace('"', '\\"')
    lines = [
        "---",
        "layout: post",
        f'title: "{safe_title}"',
    ]
    if date:
        lines.append(f"date: {date} 00:00:00 +0000")
    if description:
        safe_desc = description.replace('"', '\\"')
        lines.append(f'description: "{safe_desc}"')
    if cover:
        lines.append(f"image:\n  path: {cover}")
    if tags:
        lines.append("tags:")
        for t in tags:
            lines.append(f"  - {slugify(t)}")
    # Categories: prefer explicit ones (WordPress), else fall back to the first tag
    if not categories and tags:
        categories = [tags[0]]
    if categories:
        lines.append("categories:")
        for c in categories:
            lines.append(f"  - {slugify(c)}")
    lines.append("---\n")
    return "\n".join(lines) + "\n"


TARGET = {
    "doc_relpath": lambda slug, date: os.path.join("_posts", f"{date or '0000-00-00'}-{slug}.md"),
    "asset_dir": lambda slug: os.path.join("assets", "img", "blog", "posts", slug),
    "asset_url": lambda slug, fname: f"/assets/img/blog/posts/{slug}/{fname}",
    "front_matter": build_front_matter,
    "flavor": escape_table_pipes,
}
