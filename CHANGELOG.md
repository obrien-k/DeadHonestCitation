# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-07-26

### Added
- **A pytest suite** (`tests/`) covering the adapter registry (detection +
  metadata/body extraction per platform), `collect_sources()`, both document
  targets' front matter + `doc_relpath()`, the `data` target's `emit_citation`,
  `derive_citation()`'s provenance rules, Wayback URL math + CDX/Save-Page-Now
  discovery, the `PoliteSession` retry/backoff policy, and an end-to-end offline
  conversion of the Ghost and Markdown fixtures through both document targets.
  Entirely offline — HTTP is mocked with `responses`, the shared `PoliteSession`
  throttle is neutralized for test speed — and runs in well under a second.
- **Rich UX + resilience.** The package now speaks through a single Rich console
  (`ui.py`): the semantic status glyphs (→ ✓ ✗ ⚠ ↷ ·) are color-coded, and
  `dhc convert` wraps its source loop in a `rich.progress` bar that shares that
  console so per-source lines interleave above it. The bar disables itself on
  non-TTY output, so piped/captured runs stay clean and file outputs are
  unchanged. A root `-v/--verbose` flag enables `logging` (RichHandler on stderr)
  with per-request HTTP tracing.
- **Exception hierarchy (`exceptions.py`).** `DHCError` base with `FetchError`,
  `WaybackRateLimitError` (carries the last `Retry-After`; also a
  `requests.RequestException` so discovery keeps catching it),
  `PlatformDetectError`, `ContentNotFoundError`, and `EmitError`. These are
  raised at the network/pipeline failure sites and caught at the
  `process_url`/`process_markdown` boundary, which maps each to an `Outcome` — so
  a batch never dies on one bad source and `runlog.jsonl` gets an actionable
  reason. Exhausted 429/503 retries now raise `WaybackRateLimitError`.
- **Forum original-post model.** A ProBoards source now yields the **original post
  only** by default — a forum citation is anchored to the OP, with the rest of the
  thread available at the linked source. `--full-thread` restores every post on the
  page and, for a *live* thread, crawls the remaining paginated pages too
  (archived/local captures stay single-page, since a Wayback snapshot rarely includes
  every page).
- **Banner-to-first-post cover for forum sources.** The page is captured from the top
  (banner) down to the bottom of the first post and used as the post's cover image,
  doubling as citation evidence (described in the citation `note`). The Wayback `if_`
  raw capture keeps the archive toolbar out of frame. Best-effort (needs playwright).
- **Hacker News adapter** (`--hacker-news` / `--hn` / `-hn`; `--platform` aliases
  `hn`, `hacker-news`, `yc`, `ycombinator`). Reads a news.ycombinator.com item
  page: the submission from `table.fatitem` (title + outbound link, score/author,
  the `.age[title]` ISO date, and Show/Ask/Tell self-text), comments from
  `tr.athing.comtr` with `td.ind[indent]` as reply depth. Follows the same
  original-post model as ProBoards — the submission is the citation anchor, and
  `--full-thread` appends the comment tree as nested blockquotes.
- **`--note` / `-n`** records an editorial note on a citation (`--target data`) —
  what the capture itself cannot show, such as what became of the source after it
  was archived. `cite.html` already rendered `note`; the only thing feeding it was
  the screenshot caption, which an author's note now outranks.
- **`capture_page()`** preserves an auto-resolved page with no extractable body (a
  JS-rendered app, a landing page) as its snapshot rather than skipping it, so the
  "never silently dropped" invariant holds for markup as well as binaries.
- **`dhc --version` / `-V`** — the CLI had no version surface at all.

### Changed
- **`network/polite.py` is now a `PoliteSession`.** The module globals became a
  class holding the throttle clock and retry policy, with an explicit timeout on
  every request; one shared module-level instance keeps the process-wide clock,
  and `polite_get()` stays a thin wrapper (public API and `DHC_MIN_INTERVAL`/
  `DHC_MAX_RETRIES` tunables unchanged).
- **Restructured into a `src/` package behind one CLI.** The flat scripts became
  `src/dead_honest_citation/` — `core/` (pipeline, input layer, capture tier,
  run-log, housekeeping), `adapters/` (one module per platform), `transform/`
  (images, embeds, footnotes, cleanup, encoding repair), `targets/` (jekyll,
  commonmark, data), `network/` (polite HTTP, Wayback, screenshots), `staging`,
  and a Typer `cli/`. One entry point replaces the four scripts:
  `dhc convert | discover | stage | promote | menu | wizard | clean | prune`
  (installed by `pip install -e .`). The old scripts remain as deprecated shims
  that translate their flags and delegate. Behavior-preserving: fixture
  conversions (`tests/fixtures/`) are byte-identical to the pre-split outputs.
- Python floor is now **3.11**; dependencies moved from `requirements.txt` into
  `pyproject.toml`, with `docx`, `screenshot`, and `dev` extras (`mammoth` and
  `playwright` stay lazy imports). New runtime deps: `typer`, `rich`.
- **Typed contracts throughout.** The adapter and target registries are now
  `PlatformAdapter` / `OutputTarget` ABC subclasses; the metadata 6-tuple, the
  outcome dicts, and the citation dict became `PostMetadata` / `Outcome` /
  `Citation` dataclasses (`models.py`). Full PEP-484 annotations across the
  package; `mypy --strict` runs clean and is configured in `pyproject.toml`
  (dev extra now pulls the stub packages). Conversion output is byte-identical
  (verified against `tests/fixtures/` across all five platforms).
- **Auto-detection never dead-ends.** `detect_platform()` stays strict — it answers
  "which CMS is this?" and `None` means none — but the pipeline now cascades
  through to the `generic` adapter and then `capture_page()` instead of aborting a
  source with "Could not detect platform — re-run with --platform", advice the
  wizard gave no way to follow. An explicit `--platform` pins the choice and opts
  out of the cascade, so a forced adapter that finds no body still fails loudly.
- **Wayback chrome is stripped in both forms.** `remove_wayback_toolbar()` removed
  only the rendered toolbar (`#wm-*`, `div.wb_*`), which is injected by
  `bundle-playback.js` at render time — so a raw fetch reached the adapters still
  carrying the `<head>` rewrite include (web-static.archive.org scripts,
  `__wm.init`, Ruffle, banner styles). Both are removed now.
- **The thread model moved onto the adapter contract** — `is_thread`, `kind`,
  `thread_shot_selector`, and a `render_thread()` hook the pipeline dispatches on,
  replacing per-platform `if resolved == "proboards"` branches. `derive_citation()`
  reads `adapter.kind` instead of a hand-maintained platform→kind table, so adding
  a platform is again one module plus one registry entry.
- **`dhc wizard` reports real per-source outcomes.** It discarded every `Outcome`
  and inferred success by diffing `_posts/`, so a hard failure, an already-converted
  source, and an empty body all printed "already converted, or nothing meaningful".
- **Version is derived from the manifest.** `__version__` now reads the installed
  distribution metadata, and the polite User-Agent derives from it — the UA still
  said `0.3` after the 0.4.0 bump, with three hand-kept literals and nothing
  keeping them honest.

### Fixed
- Windows-1252 punctuation (curly quotes, dashes, ellipsis) on pages served as
  `text/html` with no charset is no longer mis-decoded into C1 control characters.
  `requests` falls back to ISO-8859-1 for such pages, turning byte `0x92` (’) into
  `U+0092` — invisible mojibake that also made YAML front matter unparseable
  (`control characters are not allowed`). `fix_cp1252_controls()` remaps the
  `0x80–0x9F` range before parsing; it's a no-op on correctly-decoded UTF-8.
- An unknown `--platform` value crashed with a raw `KeyError` out of
  `PLATFORMS[resolved]`, escaping the boundary that guarantees no exception reaches
  the caller. It is a typed `PlatformDetectError` mapped to a `failed` outcome now.

## [0.3.0] - 2026-06-20

### Changed
- **Renamed the project to DeadHonestCitation.** GitHub repo
  `obrien-k/ghost-2-jekyll` → `obrien-k/DeadHonestCitation` (old URLs redirect).
  Environment variables `ARCHIVE2MD_*` → `DHC_*` (update your `.env`). The docx
  generator marker is now `content="docx (DeadHonestCitation)"`; `detect_docx`
  keys on the `docx` substring, so previously-converted files still round-trip.
  User-Agent → `dead-honest-citation/0.3`.
- Moved the design doc to `docs/DESIGN.md`.

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

[Unreleased]: https://github.com/obrien-k/DeadHonestCitation/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/obrien-k/DeadHonestCitation/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/obrien-k/DeadHonestCitation/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/obrien-k/DeadHonestCitation/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/obrien-k/DeadHonestCitation/releases/tag/v0.1.0
