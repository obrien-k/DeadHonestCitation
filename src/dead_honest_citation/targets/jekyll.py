"""The jekyll output target: dated _posts/ files with Jekyll front matter."""

import datetime as dt
import os
from typing import ClassVar

from slugify import slugify

from ..models import PostMetadata
from .base import DocumentTarget


class JekyllTarget(DocumentTarget):
    """The default target — back-compatible YYYY-MM-DD-slug.md Jekyll posts."""

    name: ClassVar[str] = "jekyll"

    def doc_relpath(self, slug: str, date: dt.date | None) -> str:
        return os.path.join("_posts", f"{date or '0000-00-00'}-{slug}.md")

    def asset_dir(self, slug: str) -> str:
        return os.path.join("assets", "img", "blog", "posts", slug)

    def asset_url(self, slug: str, fname: str) -> str:
        return f"/assets/img/blog/posts/{slug}/{fname}"

    def front_matter(self, meta: PostMetadata) -> str:
        """Jekyll-compatible YAML front matter."""
        safe_title = meta.title.replace('"', '\\"')
        lines = [
            "---",
            "layout: post",
            f'title: "{safe_title}"',
        ]
        if meta.date:
            lines.append(f"date: {meta.date} 00:00:00 +0000")
        if meta.description:
            safe_desc = meta.description.replace('"', '\\"')
            lines.append(f'description: "{safe_desc}"')
        if meta.cover:
            lines.append(f"image:\n  path: {meta.cover}")
        if meta.tags:
            lines.append("tags:")
            for t in meta.tags:
                lines.append(f"  - {slugify(t)}")
        # Categories: prefer explicit ones (WordPress), else fall back to the first tag
        categories = meta.categories
        if not categories and meta.tags:
            categories = [meta.tags[0]]
        if categories:
            lines.append("categories:")
            for c in categories:
                lines.append(f"  - {slugify(c)}")
        lines.append("---\n")
        return "\n".join(lines) + "\n"
