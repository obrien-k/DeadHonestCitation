# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/obrien-k/ghost-2-jekyll/releases/tag/v0.1.0
