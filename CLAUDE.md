# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run (default: reads urls.txt, auto-detects the source platform per URL)
python index.py

# Sources are positional and can be mixed in one run; each is classified on its own:
#   a directory, an http(s) URL, a .html/.htm/.docx file, or a list file (urls.txt)
python index.py my-other-urls.txt                  # a list file
python index.py page.html https://example.com/post # a saved page + a live/Wayback URL
python index.py ./saved-pages/                      # a directory of .html/.htm/.docx
python index.py ./saved-pages/ --recursive          # recurse into subdirectories

# Force a platform instead of auto-detecting
python index.py urls.example.txt --wordpress # aliases: --yaaburnee, --platform wp
python index.py urls.txt --ghost             # aliases: --platform gh

# Local saved HTML files (one .html path per line) — offline, no Wayback
python index.py saved-pages.txt --wordpress  # images copied from the page's _files/ dir
python index.py saved-pages.txt --html       # generic adapter (--platform generic) for unknown CMSes

# Word documents (.docx) — converted to HTML up front (needs the `mammoth` dep),
# embedded images extracted; metadata read from docProps/core.xml
python index.py draft.docx                   # auto-detected; or force with --docx / --word

# Loose Markdown / plain-text passthrough (verbatim body; front matter lifted)
python index.py notes.md                     # .md/.markdown always passthrough
python index.py old.txt --txt                # treat .txt as content, not a list file

# Output format/layout (default jekyll). data = provenance-stamped citation objects
python index.py urls.txt --target commonmark # aliases: cm, plain, md
python index.py urls.txt --target data       # → _data/sources/<id>.yml + _sources/<id>.md
python index.py urls.txt --target data --screenshot  # render each page (needs playwright)

# Discover URLs without knowing them (discover.py): enumerate / recover / save
python discover.py example.com --contains foo        # enumerate a domain's captures
python discover.py --recover myoldforum              # recover an unknown host by name
python discover.py --save https://example.com/page/  # Save Page Now → archive permalink

# Move converted posts into the Jekyll repo (repo + source tag come from
# $ARCHIVE2MD_JEKYLL_REPO / $ARCHIVE2MD_SOURCE_TAG or .env; --repo/--tag override)
python to_jekyll.py stage output/_posts/2018-*.md      # → _drafts/<slug>.md (+source tag, +assets)
python to_jekyll.py stage --to-posts output/_posts/<f> # → _posts/<date>-<slug>.md directly
python to_jekyll.py promote <slug>                     # _drafts/<slug>.md → _posts/<date>-<slug>.md
python to_jekyll.py menu                               # interactive: list drafts, pick which to promote

# Guided interactive flow: pick source → convert → review each → stage/promote
python wizard.py

# Output housekeeping
python index.py --clean        # delete all of output/ (prompts; -y to skip the prompt)
python index.py --prune        # drop stale output (older slug dupes, orphaned asset folders)

# Lint / format (Ruff; config in pyproject.toml)
ruff check .
ruff format .
```

Linting/formatting use Ruff (`pyproject.toml`). There are no automated tests.

## Architecture

`index.py` converts archived web pages into Markdown. Input is a **Wayback/live URL, a local saved HTML file, a Word `.docx`, or loose Markdown/`.txt`**; non-HTML URLs (PDF/image/…) are **captured verbatim** instead of dropped. It is **platform-agnostic on both ends** via two symmetric registries:

- **Input adapters** (`PLATFORMS`) — recognize and read a source CMS/theme/format. Five are built in: `ghost`, `wordpress` (yaaburnee + generalized; aliases `wp`/`yaaburnee`), `generic` (opt-in `--html`, arbitrary pages), `docx` (Word; aliases `doc`/`word`), and `proboards` (forum threads; aliases `pb`/`forum`).
- **Output targets** (`TARGETS`) — decide how results are written: `jekyll` (default, back-compat), `commonmark` (aliases `cm`/`plain`/`md`), and `data` (provenance-stamped citation objects; aliases `citation`/`cite`). Selected with `--target`/`-t`.

Supporting scripts: `discover.py` finds Wayback URLs (enumerate a domain / `--recover` an unknown host by name / `--save` via Save Page Now); `netpolite.py` is the shared rate-limited HTTP layer (used by `index.py` and `discover.py`); `to_jekyll.py` stages output into a Jekyll repo's `_drafts/` and promotes to `_posts/` (interactive `menu`); `wizard.py` wraps the pipeline as a guided flow. `index.py --clean`/`--prune` handle output housekeeping.

**Input layer** — `collect_sources(tokens, recursive, txt_as_content)` resolves the positional CLI tokens into a flat, de-duplicated work list, classifying each token independently so one run can mix kinds: a **directory** expands to every source file inside (`_dir_sources()`; recursion via `--recursive`), an **http(s) URL** is itself, a **`.html`/`.htm`/`.docx`/`.md`/`.markdown` path** is one source, and any **other existing file** is a *list file* (one source per non-blank, non-`#` line — the classic `urls.txt`). `.md`/`.markdown` route to the **Markdown passthrough** (`process_markdown`); `.txt` stays a list file unless `--txt` (then it's passthrough content too). The registries are untouched by this layer; it only decides *what to feed* the per-source pipeline.

**Adapters** — each `PLATFORMS[name]` entry supplies four pieces, so adding a CMS/theme means adding one entry plus its functions:
- `detect(soup)` — recognizes the platform from page markup (used by `detect_platform()`)
- `extract_metadata(soup)` — returns `(title, date, description, tags, cover, categories)`
- `content` — a `(tag_name, attrs)` selector, **or a list of them tried in order**, locating the article body
- `clean(article)` — platform-specific body cleanup pipeline

`extract_metadata_ghost` reads Open Graph/meta tags. `extract_metadata_wordpress` is **generalized across WP themes**: each field resolves from the first source that works — title `.entry-title` → `og:title` → `h1`; date `<meta article:published_time>` → `<time datetime>` → `.post-date`/`.entry-date` text; tags from yaaburnee `tag-*` classes; categories from `.entry-meta span.post-category`. Likewise the WordPress `content` selector is a list (`.post-content`, then `.entry-content`, `.td-post-content`, `.article-content`) because themes disagree on the body wrapper — yaaburnee's 2018 captures use `.post-content`, later captures use `.entry-content`.

**Embeds / plugins** — `convert_embeds()` runs before markdownify (which silently drops `<iframe>`/`<embed>`/`<object>`). YouTube/Vimeo become labeled Markdown links; ad/Flash (`.swf`) junk is dropped; any other embed is kept as a best-effort link **and** recorded as a `⚠ NEEDS REVIEW` note, as are WordPress shortcodes (`[gallery]`, `[embed]`, …). The guiding principle: convert generic WP themes to plugin-free Markdown, preserve embeds that add personality, and surface anything needing manual attention rather than dropping it silently.

`extract_metadata_docx` reads what `docx_to_html()` planted: the `.docx`'s `docProps/core.xml` (title, author, created date) is read by `read_docx_core_props()` and written into `<meta>` tags plus a `content="docx (ghost-2-md)"` generator marker, so the docx adapter (`detect_docx`) recognizes the wrapped HTML and reads metadata like any other CMS. Embedded images are extracted to a temp dir during the mammoth conversion (`_docx_image_handler`). `mammoth` is imported lazily inside `docx_to_html()`, so the dependency is only required when actually converting a `.docx`.

**ProBoards / thread content model** — forum threads are conversations, not articles. `proboards` has no `<article>` (its `content` selector is the whole `<body>`); `clean_content_proboards` rebuilds the table-soup into attributed blocks — `**author** — date` + the message as a blockquote — keying on the 20%/80% `windowbg`/`windowbg2` post cells, the `« Reply #N on <date> »` header, and the `<hr>` message boundary. `kind` is `thread`.

**Output targets** — each `TARGETS[name]` entry supplies `doc_relpath`/`asset_dir`/`asset_url`/`front_matter`/`flavor`, or an `emit` hook to write something other than a single document. The conversion core produces `(metadata, body, assets)` and stays target-agnostic; `_emit_source()` dispatches to the target. The **`data`** target (`emit_citation`) writes a **citation object** per source — `_data/sources/<id>.yml` + `_sources/<id>.md` + a shipped plugin-free `_includes/cite.html` — with **honest provenance** (`derive_citation`): `archived` (Wayback permalink + snapshot date), `live` (URL + access date), or `local` (a saved file — never a fabricated link). `--screenshot` renders the page to a PNG via lazy/optional `playwright` and references it from the citation.

**Capture tier** — `process_url()` inspects `Content-Type` up front; a non-markup URL (PDF/image/zip/…) is preserved by `capture_binary()` (saves the bytes as an asset + emits a record/citation, `kind` from the type) rather than forced through the article pipeline. The invariant: every source ends `converted`, `captured`, `skipped`, or `failed` — never silently dropped.

**Polite HTTP + run-log** — all network I/O goes through `netpolite.polite_get()`: a global minimum interval between requests, `Retry-After` handling on 429/503, and exponential backoff on connection errors (tunable via `ARCHIVE2MD_MIN_INTERVAL`/`_MAX_RETRIES`). `process_url`/`process_markdown` return an outcome dict; `main()` appends each to `output/runlog.jsonl` (append-only coverage log) and prints a run summary.

**Processing pipeline** — `main()` resolves tokens via `collect_sources()`, the platform (`--platform`/shorthands, else auto-detected), and the target (`--target`). For each source `process_url()` (or `process_markdown()` for `.md`/`.txt`):
1. Loads the source — URLs via `polite_get()` (non-markup → `capture_binary()`); local files via `load_source()` (HTML, or `.docx` → `docx_to_html()`)
2. Strips the Wayback toolbar (`remove_wayback_toolbar()`)
3. Resolves the platform (`detect_platform()` when not forced) and selects its adapter
4. Extracts metadata via the adapter's `extract_metadata`
5. Locates article content via the adapter's `content` selector, falling back to `<article>`/`<main>`
6. Cleans the body via the adapter's `clean`
7. Derives a description from the first paragraph when the adapter supplied none
8. Downloads/localizes images (`download_images()`), rewriting `src` to the **target's** asset URL
9. Converts footnotes to `[^n]` (`convert_footnotes()`)
10. Converts HTML to Markdown via `markdownify`, then the target's `flavor` (kramdown pipe-escape)
11. Skips a page with no body, else writes via the target's `_emit_source` (jekyll post / commonmark file / data citation) and records the outcome

**Output layout** (jekyll target; other targets differ):
```
output/
  _posts/                        # YYYY-MM-DD-slug.md files
  assets/img/blog/posts/{slug}/  # downloaded images per post
  runlog.jsonl                   # append-only per-source outcomes
  # data target: _data/sources/<id>.yml, _sources/<id>.md, _includes/cite.html
```

Re-runs are idempotent — existing outputs are skipped. The `output/` directory is gitignored.

**Key dependencies:** `beautifulsoup4`, `markdownify`, `python-slugify`, `python-dateutil`, `requests`, `mammoth` (lazy — `.docx`), and optionally `playwright` (lazy — `--screenshot`).
