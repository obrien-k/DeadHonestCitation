# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Windows-1252 punctuation (curly quotes, dashes, ellipsis) on pages served as
  `text/html` with no charset is no longer mis-decoded into C1 control characters.
  `requests` falls back to ISO-8859-1 for such pages, turning byte `0x92` (’) into
  `U+0092` — invisible mojibake that also made YAML front matter unparseable
  (`control characters are not allowed`). `fix_cp1252_controls()` remaps the
  `0x80–0x9F` range before parsing; it's a no-op on correctly-decoded UTF-8.

## [0.2.0] - 2026-06-20

Two-sided generalization (pluggable output as well as input), provenance-stamped
citations, a forum adapter, broader discovery, and a polite network layer.

### Added
- **Output-target registry** (`TARGETS`) symmetric to the input adapters, selected
  with `--target`: `jekyll` (default, unchanged), `commonmark`, and `data`.
- **`data` target** — provenance-stamped citation objects: `_data/sources/<id>.yml`
  + `_sources/<id>.md` + a plugin-free `_includes/cite.html`. Provenance is honest
  by construction (`archived` / `live` / `local`).
- **ProBoards adapter** with a *thread* content model (attributed `author — date`
  blocks instead of one flattened article).
- **Markdown/plain-text passthrough** for `.md`/`.markdown` (and `.txt` under `--txt`),
  emitted verbatim with front matter lifted.
- **Capture tier** — non-HTML URLs (PDF/image/…) are preserved verbatim rather than
  dropped; every source ends converted / captured / skipped / failed.
- **`discover.py`** gains host recovery (`--recover` probes hosting platforms by
  name) and Save Page Now (`--save`).
- **Optional screenshots** (`--screenshot`, lazy `playwright`) referenced from
  citations.
- **`netpolite.py`** — shared rate-limited HTTP layer (global interval, Retry-After,
  backoff) used by `index.py` and `discover.py`.
- **Run-log** — per-source outcomes appended to `output/runlog.jsonl` + a run summary.

### Fixed
- Decode HTML-encoded `&amp;` in discovered capture URLs so they resolve correctly.

## [0.1.0] - 2026-06-20

First public-ready release: a platform-agnostic archive→Markdown converter.

### Added
- Platform adapter registry (`PLATFORMS`) with four built-in adapters — Ghost,
  WordPress (generalized across themes), a generic HTML adapter, and Word `.docx`.
- Input layer (`collect_sources`) that mixes source kinds in one run: Wayback/live
  URLs, saved `.html`/`.htm` files, `.docx` documents, directories (`--recursive`),
  and classic list files.
- `discover.py` — enumerate a domain's Wayback Machine captures via the CDX API and
  emit them as sources, with a `--contains` slug filter and `--newest`/`-o` options.
- `to_jekyll.py` — stage converted posts into a Jekyll repo's `_drafts/` and promote
  them into `_posts/`, with an interactive `menu`.
- `wizard.py` — guided, interactive end-to-end flow.
- Embed handling (YouTube/Vimeo → links, Flash/ad junk dropped) with `⚠ NEEDS
  REVIEW` notes for anything that needs a human; footnote conversion to `[^n]`.
- Output housekeeping (`--clean`, `--prune`) and idempotent re-runs.
- Environment-based configuration (`ARCHIVE2MD_JEKYLL_REPO`, `ARCHIVE2MD_SOURCE_TAG`)
  via a no-dependency `.env` loader, with `.env.example` and `urls.example.txt`.
- Ruff linting/formatting configured in `pyproject.toml`.

### Changed
- Generalized the converter from a Ghost-only exporter into a platform-agnostic tool.
- Rewrote `README.md` and `CLAUDE.md` to match the current architecture.

### Fixed
- Image and cover downloads from the Wayback Machine (prefers `im_` raw captures).
- Escape `|` in Markdown link text so kramdown doesn't misread it as a table.

[0.2.0]: https://github.com/obrien-k/ghost-2-jekyll/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/obrien-k/ghost-2-jekyll/releases/tag/v0.1.0
