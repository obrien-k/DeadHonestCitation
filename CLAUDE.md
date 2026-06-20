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
```

There are no tests or linters configured.

## Architecture

Single-file script (`index.py`) that converts archived blog posts into Jekyll-compatible Markdown files. Input is a **Wayback Machine/live URL, a local saved HTML file, or a Word `.docx`** (`load_source()` branches on `is_local_source()`; local HTML copies images from the sibling `<name>_files/` dir instead of downloading; `.docx` is converted to HTML up front by `docx_to_html()`). It is **platform-agnostic**: a registry of adapters (`PLATFORMS`) handles each source CMS/theme. Four are built in — `ghost`, `wordpress` (the yaaburnee theme + generalized; aliases `wp`/`yaaburnee`), `generic` (opt-in `--html`/`--platform generic`, for arbitrary pages), and `docx` (Word documents; aliases `doc`/`word`). A companion `to_jekyll.py` stages output into a Jekyll repo's `_drafts/` and promotes drafts into `_posts/` (with an interactive `menu`); `wizard.py` wraps the whole pipeline as a guided flow (pick source → convert → per-post keep/skip/draft/post review → stage → promote). `index.py --clean`/`--prune` handle output housekeeping.

**Input layer** — `collect_sources(tokens, recursive)` is the input-agnostic seam that resolves the positional CLI tokens into a flat, de-duplicated work list, classifying each token independently so one run can mix kinds: a **directory** expands to every `*.html`/`*.htm`/`*.docx` inside (`_dir_sources()`; recursion opt-in via `--recursive`), an **http(s) URL** is itself, a **`.html`/`.htm`/`.docx` path** is one local page/doc, and any **other existing file** is treated as a *list file* (one source per non-blank, non-`#` line — the classic `urls.txt`). The adapter registry is untouched by this layer; it only decides *what to feed* the per-source pipeline.

**Adapters** — each `PLATFORMS[name]` entry supplies four pieces, so adding a CMS/theme means adding one entry plus its functions:
- `detect(soup)` — recognizes the platform from page markup (used by `detect_platform()`)
- `extract_metadata(soup)` — returns `(title, date, description, tags, cover, categories)`
- `content` — a `(tag_name, attrs)` selector, **or a list of them tried in order**, locating the article body
- `clean(article)` — platform-specific body cleanup pipeline

`extract_metadata_ghost` reads Open Graph/meta tags. `extract_metadata_wordpress` is **generalized across WP themes**: each field resolves from the first source that works — title `.entry-title` → `og:title` → `h1`; date `<meta article:published_time>` → `<time datetime>` → `.post-date`/`.entry-date` text; tags from yaaburnee `tag-*` classes; categories from `.entry-meta span.post-category`. Likewise the WordPress `content` selector is a list (`.post-content`, then `.entry-content`, `.td-post-content`, `.article-content`) because themes disagree on the body wrapper — yaaburnee's 2018 captures use `.post-content`, later captures use `.entry-content`.

**Embeds / plugins** — `convert_embeds()` runs before markdownify (which silently drops `<iframe>`/`<embed>`/`<object>`). YouTube/Vimeo become labeled Markdown links; ad/Flash (`.swf`) junk is dropped; any other embed is kept as a best-effort link **and** recorded as a `⚠ NEEDS REVIEW` note, as are WordPress shortcodes (`[gallery]`, `[embed]`, …). The guiding principle: convert generic WP themes to plugin-free Markdown, preserve embeds that add personality, and surface anything needing manual attention rather than dropping it silently.

`extract_metadata_docx` reads what `docx_to_html()` planted: the `.docx`'s `docProps/core.xml` (title, author, created date) is read by `read_docx_core_props()` and written into `<meta>` tags plus a `content="docx (ghost-2-md)"` generator marker, so the docx adapter (`detect_docx`) recognizes the wrapped HTML and reads metadata like any other CMS. Embedded images are extracted to a temp dir during the mammoth conversion (`_docx_image_handler`). `mammoth` is imported lazily inside `docx_to_html()`, so the dependency is only required when actually converting a `.docx`.

**Processing pipeline** — `main()` resolves the positional source tokens via `collect_sources()` and the platform (forced via `--platform`/`--ghost`/`--wordpress`/`--docx`, else auto-detected per source). For each source `process_url()`:
1. Loads the source (`load_source()` — `fetch()` with retry for URLs, or reads the file for a local HTML path)
2. Strips Wayback Machine toolbar (`remove_wayback_toolbar()`)
3. Resolves the platform (`detect_platform()` when not forced) and selects its adapter
4. Extracts metadata via the adapter's `extract_metadata`
5. Locates article content via the adapter's `content` selector, falling back to `<article>`/`<main>`
6. Cleans the body via the adapter's `clean` (Ghost: `clean_ghost_classes` + `normalize_headings`; WordPress: also `clean_wordpress_cruft`, which strips Kiwi share bars and related-article blocks)
7. Derives a description from the first paragraph when the adapter supplied none (WordPress)
8. Downloads and localizes images (`download_images()`), rewrites `src` to `/assets/img/blog/posts/{slug}/`
9. Converts footnotes to Markdown `[^n]` syntax (`convert_footnotes()`)
10. Converts HTML to Markdown via `markdownify`
11. Skips a page that renders no body (e.g. a homepage template), else writes `output/_posts/YYYY-MM-DD-{slug}.md` with Jekyll YAML front matter

**Output layout:**
```
output/
  _posts/                        # YYYY-MM-DD-slug.md files
  assets/img/blog/posts/{slug}/  # Downloaded images per post
```

Re-runs are idempotent — existing `.md` files are skipped. The `output/` directory is gitignored.

**Key dependencies:** `beautifulsoup4`, `markdownify`, `python-slugify`, `python-dateutil`, `requests`, and `mammoth` (lazy — only for `.docx` conversion)
