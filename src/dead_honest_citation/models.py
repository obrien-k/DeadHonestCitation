"""Typed data structures passed between the pipeline, adapters, and targets."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

# The terminal states of the run-log invariant: every source ends in exactly one,
# never silently dropped.
Status = Literal["converted", "captured", "skipped", "failed"]

# How verifiable a source is — the provenance ladder. A rung must never lie:
# `local` never claims a public link, `archived` carries its real permalink.
Provenance = Literal["archived", "live", "local"]


@dataclass
class PostMetadata:
    """Everything extracted about one source, before the body is written.

    Attributes:
        title: Document title (never empty; adapters fall back to "Untitled").
        date: Publish date, or None when no source yielded one.
        description: Short summary; derived from the first paragraph when the
            adapter supplied none.
        tags: Tag names as found (slugified only at write time).
        cover: In-document URL of the localized cover image, or "".
        categories: Explicit categories (WordPress); targets may derive one
            from the first tag when empty.
        screenshot: In-document URL of a rendered page capture, or None.
        screenshot_note: Caption describing what the screenshot shows.
        note: Editorial note for the citation — what the capture itself cannot
            show, such as what became of the source afterwards. Author-supplied
            (--note); outranks screenshot_note as the rendered citation note.
    """

    title: str
    date: dt.date | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    cover: str = ""
    categories: list[str] = field(default_factory=list)
    screenshot: str | None = None
    screenshot_note: str = ""
    note: str = ""


@dataclass(frozen=True)
class Citation:
    """Provenance fields for one source — honest by construction.

    Attributes:
        provenance: Where the copy stands on the verifiability ladder.
        source_url: The original URL (or bare filename for a local copy).
        archive_url: Public Wayback permalink; only set when provenance is
            "archived".
        captured_at: Snapshot date (archived) or access date (live), ISO
            YYYY-MM-DD; None for a local copy.
        kind: Content kind — post / page / thread / document / image / file.
    """

    provenance: Provenance
    source_url: str | None
    archive_url: str | None
    captured_at: str | None
    kind: str


@dataclass(frozen=True)
class Outcome:
    """One source's terminal result, as appended to the run log.

    Attributes:
        status: The terminal state (converted / captured / skipped / failed).
        output: Repo-relative path of what was written, when anything was.
        reason: Why the source skipped/failed, or review notes for a
            conversion (e.g. embeds kept as links).
    """

    status: Status
    output: str | None = None
    reason: str | None = None
