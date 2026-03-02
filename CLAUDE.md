# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run (default: reads urls.txt)
python index.py

# Run with a custom URL file
python index.py my-other-urls.txt
```

There are no tests or linters configured.

## Architecture

Single-file script (`index.py`) that converts archived Ghost blog posts (via Wayback Machine URLs) into Jekyll-compatible Markdown files.

**Processing pipeline** — `main()` reads `urls.txt`, then for each URL `process_url()`:
1. Fetches with retry logic (`fetch()`)
2. Strips Wayback Machine toolbar (`remove_wayback_toolbar()`)
3. Extracts metadata from Open Graph/meta tags (`extract_metadata()`) — title, date, description, tags, cover image
4. Locates article content: prefers `<section class="gh-content">`, falls back to `<article>` or `<main>`
5. Downloads and localizes images (`download_images()`), rewrites `src` to `/assets/img/blog/posts/{slug}/`
6. Cleans Ghost/Koenig CSS classes (`clean_ghost_classes()`) and normalizes duplicate `<h1>` tags (`normalize_headings()`)
7. Converts footnotes to Markdown `[^n]` syntax (`convert_footnotes()`)
8. Converts HTML to Markdown via `markdownify`
9. Writes `output/_posts/YYYY-MM-DD-{slug}.md` with Jekyll YAML front matter

**Output layout:**
```
output/
  _posts/                        # YYYY-MM-DD-slug.md files
  assets/img/blog/posts/{slug}/  # Downloaded images per post
```

Re-runs are idempotent — existing `.md` files are skipped. The `output/` directory is gitignored.

**Key dependencies:** `beautifulsoup4`, `markdownify`, `python-slugify`, `python-dateutil`, `requests`
