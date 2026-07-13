"""The commonmark output target: flat, SSG-neutral Markdown files."""

import datetime as dt
import os
from typing import ClassVar

from slugify import slugify

from ..models import PostMetadata
from .base import DocumentTarget


class CommonMarkTarget(DocumentTarget):
    """Plain slug.md files with minimal, SSG-neutral front matter."""

    name: ClassVar[str] = "commonmark"

    def doc_relpath(self, slug: str, date: dt.date | None) -> str:
        return f"{slug}.md"

    def asset_dir(self, slug: str) -> str:
        return os.path.join("assets", slug)

    def asset_url(self, slug: str, fname: str) -> str:
        return f"assets/{slug}/{fname}"

    def front_matter(self, meta: PostMetadata) -> str:
        """Minimal YAML front matter (no Jekyll-specific keys)."""
        safe_title = meta.title.replace('"', '\\"')
        lines = ["---", f'title: "{safe_title}"']
        if meta.date:
            lines.append(f"date: {meta.date}")
        if meta.description:
            safe_desc = meta.description.replace('"', '\\"')
            lines.append(f'description: "{safe_desc}"')
        if meta.tags:
            lines.append("tags:")
            for t in meta.tags:
                lines.append(f"  - {slugify(t)}")
        lines.append("---\n")
        return "\n".join(lines) + "\n"
