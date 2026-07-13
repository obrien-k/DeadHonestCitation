# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup — the package installs a single CLI entry point, `dhc`
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"        # dev extra: pytest, responses, mypy, ruff
# optional extras: .[docx] (mammoth), .[screenshot] (playwright + `playwright install chromium`)

# Convert (default: reads urls.txt, auto-detects the source platform per URL)
dhc convert

# Sources are positional and can be mixed in one run; each is classified on its own:
#   a directory, an http(s) URL, a .html/.htm/.docx file, or a list file (urls.txt)
dhc convert my-other-urls.txt                  # a list file
dhc convert page.html https://example.com/post # a saved page + a live/Wayback URL
dhc convert ./saved-pages/                     # a directory of .html/.htm/.docx
dhc convert ./saved-pages/ --recursive         # recurse into subdirectories

# Force a platform instead of auto-detecting
dhc convert urls.example.txt --wordpress # aliases: --yaaburnee, --platform wp
dhc convert urls.txt --ghost             # aliases: --platform gh

# Local saved HTML files (one .html path per line) — offline, no Wayback
dhc convert saved-pages.txt --wordpress  # images copied from the page's _files/ dir
dhc convert saved-pages.txt --html       # generic adapter (--platform generic) for unknown CMSes

# Word documents (.docx) — converted to HTML up front (needs the docx extra),
# embedded images extracted; metadata read from docProps/core.xml
dhc convert draft.docx                   # auto-detected; or force with --docx / --word

# Loose Markdown / plain-text passthrough (verbatim body; front matter lifted)
dhc convert notes.md                     # .md/.markdown always passthrough
dhc convert old.txt --txt                # treat .txt as content, not a list file

# Output format/layout (default jekyll). data = provenance-stamped citation objects
dhc convert urls.txt --target commonmark # aliases: cm, plain, md
dhc convert urls.txt --target data       # → _data/sources/<id>.yml + _sources/<id>.md
dhc convert urls.txt --target data --screenshot  # render each page (needs playwright)

# Forum threads: original post only by default; --full-thread keeps every post
dhc convert thread-url --full-thread

# Discover URLs without knowing them: enumerate / recover / save
dhc discover domain example.com --contains foo   # enumerate a domain's captures
dhc discover recover myoldforum                  # recover an unknown host by name
dhc discover save https://example.com/page/      # Save Page Now → archive permalink

# Move converted posts into the Jekyll repo (repo + source tag come from
# $DHC_JEKYLL_REPO / $DHC_SOURCE_TAG or .env; --repo/--tag override)
dhc stage output/_posts/2018-*.md        # → _drafts/<slug>.md (+source tag, +assets)
dhc stage --to-posts output/_posts/<f>   # → _posts/<date>-<slug>.md directly
dhc promote <slug>                       # _drafts/<slug>.md → _posts/<date>-<slug>.md
dhc menu                                 # interactive: list drafts, pick which to promote

# Guided interactive flow: pick source → convert → review each → stage/promote
dhc wizard

# Output housekeeping
dhc clean          # delete all of output/ (prompts; -y to skip the prompt)
dhc prune          # drop stale output (older slug dupes, orphaned asset folders)

# Lint / format / typecheck (config in pyproject.toml)
ruff check .
ruff format .
mypy          # strict; covers src/

# Tests — offline, mocked HTTP (responses), no network; runs in well under a second
pytest
```

The old script entry points (`python index.py`, `discover.py`, `to_jekyll.py`, `wizard.py`)
are deprecated shims that translate their flags and delegate to `dhc`. `tests/fixtures/`
holds offline sample pages per platform, used by both the pytest suite (`tests/`) and
manual smoke-testing (the byte-diff harness in the project's verification notes).

## Architecture

The code lives in `src/dead_honest_citation/`. It converts archived web pages into
Markdown: input is a **Wayback/live URL, a local saved HTML file, a Word `.docx`, or
loose Markdown/`.txt`**; non-HTML URLs (PDF/image/…) are **captured verbatim** instead
of dropped. It is **platform-agnostic on both ends** via two symmetric registries:

- **Input adapters** (`adapters.PLATFORMS`) — recognize and read a source CMS/theme/format.
  Five are built in, one module each under `adapters/`: `ghost`, `wordpress` (yaaburnee +
  generalized; aliases `wp`/`yaaburnee`), `generic` (opt-in `--html`, arbitrary pages),
  `docx` (Word; aliases `doc`/`word`), and `proboards` (forum threads; aliases `pb`/`forum`).
- **Output targets** (`targets.TARGETS`) — decide how results are written, one module each
  under `targets/`: `jekyll` (default, back-compat), `commonmark` (aliases `cm`/`plain`/`md`),
  and `data` (provenance-stamped citation objects; aliases `citation`/`cite`).
  Selected with `--target`/`-t`.

Package layout (each module's role):

- `config.py` — output paths (`output/`, `_posts`, assets, `runlog.jsonl`), the
  no-dependency `.env` loader, and the `DHC_JEKYLL_REPO`/`DHC_SOURCE_TAG` defaults.
- `core/pipeline.py` — `process_url()` / `process_markdown()`, the per-source orchestration.
- `core/sources.py` — the input layer: `collect_sources()`, `load_source()`, extension
  classification (`SOURCE_EXTS`, `MD_EXTS`).
- `core/capture.py` — the capture tier: `is_markup()`, `capture_binary()`.
- `core/runlog.py` — the append-only `runlog.jsonl` writer (`log_run()` takes an `Outcome`).
- `core/housekeeping.py` — `clean_output()`, `prune_output()`.
- `models.py` — the shared dataclasses: `PostMetadata`, `Citation`, `Outcome`.
- `adapters/` — the platform registry (`PLATFORMS`, `PLATFORM_ALIASES`, `detect_platform()`).
- `transform/` — platform-independent HTML→MD machinery: `cleanup` (shared scrubbers),
  `images` (download/copy + src rewriting), `embeds`, `footnotes`, `frontmatter`
  (passthrough lifting), `encoding` (cp1252 C1 repair).
- `targets/` — the target registry and `resolve_target()`; writing dispatches through
  each target's `write()`; `targets/data.py` holds `derive_citation()` + the cite include.
- `network/polite.py` — the shared rate-limited HTTP layer. The policy lives on a
  `PoliteSession` (global minimum interval, explicit per-request timeouts, Retry-After
  on 429/503, exponential backoff; tunable via `DHC_MIN_INTERVAL`/`DHC_MAX_RETRIES`);
  one module-level instance (`_session`) is shared process-wide so the throttle clock
  survives across callers, and `polite_get()` is a thin wrapper delegating to it (public
  API unchanged). Exhausted 429/503 retries raise `WaybackRateLimitError`.
- `exceptions.py` — the `DHCError` hierarchy (`FetchError`, `WaybackRateLimitError` —
  also a `requests.RequestException` so discovery keeps catching it —,
  `PlatformDetectError`, `ContentNotFoundError`, `EmitError`). Raised at the pipeline/
  network failure sites and caught at the `process_url`/`process_markdown` boundary,
  which maps each to an `Outcome` so a batch never dies on one source.
- `ui.py` — the Rich `Console` singleton (stdout) + a stderr console + `logging` setup
  (`setup_logging()` behind the root `-v/--verbose` flag). Status glyphs (→ ✓ ✗ ⚠ ↷ ·)
  are color-coded via `status`/`detail`/`success`/`warn`/`error` helpers; `cli/convert.py`
  wraps the source loop in a `rich.progress` bar that shares this console (disabled on
  non-TTY, so piped/captured output stays clean).
- `network/wayback.py` — Wayback URL math (`WAYBACK_RE`, `unwrap_wayback()`,
  `wayback_image_candidates()`, `wayback_raw()`) and discovery (CDX enumerate,
  host recovery, Save Page Now).
- `network/screenshot.py` — lazy/optional playwright page rendering.
- `staging.py` — stage/promote posts into a Jekyll repo (`stage_one()`, `promote_one()`,
  tag injection, asset copying).
- `cli/` — the Typer app: `convert.py` (+ clean/prune), `discover.py` (sub-app),
  `stage.py` (stage/promote/menu), `wizard.py` (guided flow).

**Adapters** — each `PLATFORMS[name]` entry is a `PlatformAdapter` subclass
(`adapters/base.py` defines the ABC), so adding a CMS/theme means one
`adapters/<name>.py` module plus one registry entry:
- `detect(soup)` — recognizes the platform from page markup (used by `detect_platform()`)
- `extract_metadata(soup)` — returns a `PostMetadata` dataclass (`models.py`)
- `content` — a `(tag_name, attrs)` selector, **or a list of them tried in order**, locating the article body
- `clean(article)` — platform-specific body cleanup pipeline

The Ghost adapter reads Open Graph/meta tags. The WordPress extraction is
**generalized across WP themes**: each field resolves from the first source that works —
title `.entry-title` → `og:title` → `h1`; date `<meta article:published_time>` →
`<time datetime>` → `.post-date`/`.entry-date` text; tags from yaaburnee `tag-*` classes;
categories from `.entry-meta span.post-category`. Likewise the WordPress `content`
selector is a list (`.post-content`, then `.entry-content`, `.td-post-content`,
`.article-content`) because themes disagree on the body wrapper.

**Embeds / plugins** — `transform.embeds.convert_embeds()` runs before markdownify (which
silently drops `<iframe>`/`<embed>`/`<object>`). YouTube/Vimeo become labeled Markdown
links; ad/Flash (`.swf`) junk is dropped; any other embed is kept as a best-effort link
**and** recorded as a `⚠ NEEDS REVIEW` note, as are WordPress shortcodes (`[gallery]`,
`[embed]`, …). The guiding principle: convert generic WP themes to plugin-free Markdown,
preserve embeds that add personality, and surface anything needing manual attention
rather than dropping it silently.

`adapters/docx.py` wraps Word documents: `docx_to_html()` plants the `.docx`'s
`docProps/core.xml` metadata (title, author, created) as `<meta>` tags plus a
`content="docx (DeadHonestCitation)"` generator marker, so `detect_docx` recognizes the
wrapped HTML and reads metadata like any other CMS. Embedded images are extracted to a
temp dir during the mammoth conversion. `mammoth` is imported lazily inside
`docx_to_html()`, so the dependency is only required when actually converting a `.docx`.

**ProBoards / thread content model** — forum threads are conversations, not articles.
`proboards` has no `<article>` (its `content` selector is the whole `<body>`);
`adapters/proboards.py` rebuilds the table-soup into attributed blocks — `**author** — date`
+ the message as a blockquote — keying on the 20%/80% `windowbg`/`windowbg2` post cells,
the `« Reply #N on <date> »` header, and the `<hr>` message boundary. **Original-post
model**: by default only the OP is kept (the citation anchor); `--full-thread` keeps every
post and, for a live thread, crawls later pages (`proboards_collect()`). A forum source
also gets an automatic banner→first-post screenshot as its cover/citation evidence.
`kind` is `thread`.

**Output targets** — each `TARGETS[name]` entry is an `OutputTarget` subclass
(`targets/base.py`): `doc_relpath`/`asset_dir`/`asset_url`/`flavor` plus a `write()`
hook — `DocumentTarget` subclasses supply `front_matter()` and inherit the document
writer; citation targets override `write()` outright (`is_citation` drives the
pipeline's cover/screenshot handling). The conversion core produces
`(PostMetadata, body, assets)` and stays target-agnostic; `target.write()` dispatches. The **`data`** target
(`emit_citation`) writes a **citation object** per source — `_data/sources/<id>.yml` +
`_sources/<id>.md` + a shipped plugin-free `_includes/cite.html` — with **honest
provenance** (`derive_citation`): `archived` (Wayback permalink + snapshot date), `live`
(URL + access date), or `local` (a saved file — never a fabricated link).

**Capture tier** — `process_url()` inspects `Content-Type` up front; a non-markup URL
(PDF/image/zip/…) is preserved by `capture_binary()` (saves the bytes as an asset +
emits a record/citation, `kind` from the type) rather than forced through the article
pipeline. The invariant: every source ends `converted`, `captured`, `skipped`, or
`failed` — never silently dropped.

**Processing pipeline** — `dhc convert` resolves tokens via `collect_sources()`, the
platform (`--platform`/shorthands, else auto-detected), and the target (`--target`).
For each source `process_url()` (or `process_markdown()` for `.md`/`.txt`):
1. Loads the source — URLs via `polite_get()` (non-markup → `capture_binary()`); local files via `load_source()` (HTML, or `.docx` → `docx_to_html()`)
2. Strips the Wayback toolbar (`remove_wayback_toolbar()`)
3. Resolves the platform (`detect_platform()` when not forced) and selects its adapter
4. Extracts metadata via the adapter's `extract_metadata`
5. Locates article content via the adapter's `content` selector, falling back to `<article>`/`<main>`
6. Cleans the body via the adapter's `clean` (forum sources: OP-only render)
7. Derives a description from the first paragraph when the adapter supplied none
8. Downloads/localizes images (`download_images()`), rewriting `src` to the **target's** asset URL
9. Converts footnotes to `[^n]` (`convert_footnotes()`)
10. Converts HTML to Markdown via `markdownify`, then the target's `flavor` (kramdown pipe-escape)
11. Skips a page with no body, else writes via the target's emit path (jekyll post / commonmark file / data citation) and records the outcome

**Output layout** (jekyll target; other targets differ):
```
output/
  _posts/                        # YYYY-MM-DD-slug.md files
  assets/img/blog/posts/{slug}/  # downloaded images per post
  runlog.jsonl                   # append-only per-source outcomes
  # data target: _data/sources/<id>.yml, _sources/<id>.md, _includes/cite.html
```

Re-runs are idempotent — existing outputs are skipped. The `output/` directory is gitignored.

**Key dependencies:** `beautifulsoup4`, `markdownify`, `python-slugify`, `python-dateutil`,
`requests`, `typer`, `rich`, plus lazy/optional `mammoth` (`.docx`) and `playwright`
(`--screenshot`). Python 3.11+.
