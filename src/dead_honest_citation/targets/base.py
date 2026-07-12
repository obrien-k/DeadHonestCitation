"""The output-target contract: how a converted source is written to disk."""

import datetime as dt
import os
import re
from abc import ABC, abstractmethod
from typing import ClassVar

from ..config import OUTPUT_DIR
from ..models import PostMetadata


def escape_table_pipes(markdown: str) -> str:
    """Escape | inside link text so kramdown/GFM won't read it as table syntax."""
    return re.sub(
        r"\[([^\]]*\|[^\]]*)\]",
        lambda m: "[" + m.group(1).replace("|", r"\|") + "]",
        markdown,
    )


class OutputTarget(ABC):
    """One way of writing results — front-matter format, file naming/layout,
    asset paths, and Markdown-flavor tweaks.

    The conversion core stays target-agnostic (it produces metadata + body +
    assets), so supporting another static-site generator means one subclass
    plus a targets.TARGETS entry.

    Attributes:
        name: Registry key, also what --target accepts.
        is_citation: True when the target emits citation records rather than
            documents (drives cover/screenshot handling in the pipeline).
    """

    name: ClassVar[str]
    is_citation: ClassVar[bool] = False

    @abstractmethod
    def doc_relpath(self, slug: str, date: dt.date | None) -> str:
        """Path (under OUTPUT_DIR) for the source's document/record file."""

    @abstractmethod
    def asset_dir(self, slug: str) -> str:
        """Directory (under OUTPUT_DIR) holding that source's images."""

    @abstractmethod
    def asset_url(self, slug: str, fname: str) -> str:
        """The in-document URL for a localized image."""

    def flavor(self, markdown: str) -> str:
        """Post-process the Markdown body for this target's renderer."""
        return escape_table_pipes(markdown)

    @abstractmethod
    def write(
        self,
        doc_relpath: str,
        url: str,
        base_dir: str | None,
        platform_name: str,
        slug: str,
        meta: PostMetadata,
        body: str,
        footnotes: str,
        kind: str | None = None,
    ) -> str:
        """Write one converted source; return the relpath of what was written.

        Args:
            doc_relpath: Destination path from doc_relpath() (documents only;
                citation targets derive their own layout).
            url: The source URL or local path (provenance input).
            base_dir: Directory of a local source, or None for a fetched URL.
            platform_name: Resolved adapter name (or "txt"/"capture" for the
                passthrough and capture lanes).
            slug: The source's stable slug.
            meta: Extracted metadata.
            body: The Markdown body.
            footnotes: Markdown footnote block ("" when none).
            kind: Override for the citation kind (e.g. a captured image).
        """


class DocumentTarget(OutputTarget):
    """A target that writes one front-mattered Markdown document per source."""

    @abstractmethod
    def front_matter(self, meta: PostMetadata) -> str:
        """The front-matter block for one document."""

    def write(
        self,
        doc_relpath: str,
        url: str,
        base_dir: str | None,
        platform_name: str,
        slug: str,
        meta: PostMetadata,
        body: str,
        footnotes: str,
        kind: str | None = None,
    ) -> str:
        filepath = os.path.join(OUTPUT_DIR, doc_relpath)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.front_matter(meta))
            f.write(body)
            if footnotes.strip():
                f.write(footnotes)
        return doc_relpath
