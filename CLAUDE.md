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

# Run with a custom URL file
python index.py my-other-urls.txt

# Force a platform instead of auto-detecting
python index.py wuubi-urls.txt --wordpress   # aliases: --yaaburnee, --platform wp
python index.py urls.txt --ghost             # aliases: --platform gh
```

There are no tests or linters configured.

## Architecture

Single-file script (`index.py`) that converts archived blog posts (via Wayback Machine URLs) into Jekyll-compatible Markdown files. It is **platform-agnostic**: a registry of adapters (`PLATFORMS`) handles each source CMS/theme. Two are built in — `ghost` and `wordpress` (the yaaburnee theme; aliases `wp`/`yaaburnee`).

**Adapters** — each `PLATFORMS[name]` entry supplies four pieces, so adding a CMS/theme means adding one entry plus its functions:
- `detect(soup)` — recognizes the platform from page markup (used by `detect_platform()`)
- `extract_metadata(soup)` — returns `(title, date, description, tags, cover, categories)`
- `content` — `(tag_name, attrs)` selector locating the article body
- `clean(article)` — platform-specific body cleanup pipeline

`extract_metadata_ghost` reads Open Graph/meta tags; `extract_metadata_wordpress` reads the yaaburnee theme's `.entry-title` / `.post-date` / `tag-*` classes / `.entry-meta span.post-category`.

**Processing pipeline** — `main()` reads the URL file and resolves the platform (forced via `--platform`/`--ghost`/`--wordpress`, else auto-detected per URL). For each URL `process_url()`:
1. Fetches with retry logic (`fetch()`)
2. Strips Wayback Machine toolbar (`remove_wayback_toolbar()`)
3. Resolves the platform (`detect_platform()` when not forced) and selects its adapter
4. Extracts metadata via the adapter's `extract_metadata`
5. Locates article content via the adapter's `content` selector, falling back to `<article>`/`<main>`
6. Cleans the body via the adapter's `clean` (Ghost: `clean_ghost_classes` + `normalize_headings`; WordPress: also `clean_wordpress_cruft`, which strips Kiwi share bars and related-article blocks)
7. Derives a description from the first paragraph when the adapter supplied none (WordPress)
8. Downloads and localizes images (`download_images()`), rewrites `src` to `/assets/img/blog/posts/{slug}/`
9. Converts footnotes to Markdown `[^n]` syntax (`convert_footnotes()`)
10. Converts HTML to Markdown via `markdownify`
11. Writes `output/_posts/YYYY-MM-DD-{slug}.md` with Jekyll YAML front matter

**Output layout:**
```
output/
  _posts/                        # YYYY-MM-DD-slug.md files
  assets/img/blog/posts/{slug}/  # Downloaded images per post
```

Re-runs are idempotent — existing `.md` files are skipped. The `output/` directory is gitignored.

**Key dependencies:** `beautifulsoup4`, `markdownify`, `python-slugify`, `python-dateutil`, `requests`
