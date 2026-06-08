# archive-2-md

Convert archived blog posts — captured on the [Wayback Machine](https://web.archive.org/) — into Jekyll-compatible Markdown, deterministically and without rewriting the prose.

The tool is **platform-agnostic**: a small registry of *adapters* teaches it how to read each source CMS or theme. Two ship in the box — **Ghost** and **WordPress** (the yaaburnee theme) — and adding another is a single registry entry. The output is plain Markdown with [kramdown](https://kramdown.gettalong.org/)-friendly front matter and footnotes, so posts drop straight into a Jekyll site.

> The repository is still named `ghost-2-md` for historical reasons; it started as a Ghost-only exporter and grew into a general archive→Markdown converter.

## What it does

For each archived URL it:

- Fetches the page from the Wayback Machine, with retry/back-off on rate limits
- Strips the Wayback Machine toolbar injected into archived pages
- **Auto-detects the source platform** from the markup (or you can force one)
- Extracts title, date, description, tags, categories, and cover image via the platform's adapter
- Locates the article body via the adapter's content selector (falling back to `<article>`/`<main>`)
- Runs the adapter's cleanup pipeline (e.g. drops Ghost/Koenig CSS classes, WordPress share bars and related-post blocks)
- Downloads and localizes every image, rewriting `src` to a repo-relative asset path
- Converts footnotes to native Markdown `[^1]` syntax (kramdown-compatible)
- Converts HTML → Markdown (headings, links, tables, code blocks) and escapes `|` so kramdown won't misread link text as a table
- Writes `YYYY-MM-DD-slug.md` with Jekyll YAML front matter

Re-runs are idempotent — posts whose `.md` already exists are skipped.

## Architecture

A single script, `index.py`, built around a **platform adapter registry** (`PLATFORMS`). Each adapter supplies four pieces, so supporting a new CMS/theme means adding one entry plus its functions — no changes to the processing pipeline:

| Piece | Responsibility |
|-------|----------------|
| `detect(soup)` | Recognize the platform from page markup (drives auto-detection) |
| `extract_metadata(soup)` | Return `(title, date, description, tags, cover, categories)` |
| `content` | A `(tag_name, attrs)` selector locating the article body |
| `clean(article)` | Platform-specific body-cleanup pipeline |

The pipeline in `process_url()` is platform-neutral — it calls into the resolved adapter at each step:

1. `fetch()` — GET with retry logic
2. `remove_wayback_toolbar()` — strip the archive chrome
3. `detect_platform()` — pick the adapter (skipped when forced via `--platform`)
4. adapter `extract_metadata` — pull front-matter fields
5. adapter `content` selector — locate the body
6. adapter `clean` — scrub theme cruft
7. derive a description from the first paragraph when the adapter supplied none
8. `download_images()` — localize images to `assets/img/blog/posts/{slug}/`
9. `convert_footnotes()` — HTML footnotes → `[^n]`
10. `markdownify` — HTML → Markdown
11. write `output/_posts/YYYY-MM-DD-{slug}.md` with front matter

### Adding a platform

1. Write `detect_<name>(soup)`, `extract_metadata_<name>(soup)`, and `clean_content_<name>(article)`.
2. Register them in `PLATFORMS` with a `content` selector.
3. (Optional) add CLI aliases in `PLATFORM_ALIASES`.

Auto-detection and the `--platform` flag pick the new adapter up automatically.

## Output layout

```
output/
  _posts/                        # YYYY-MM-DD-slug.md, ready for Jekyll
  assets/img/blog/posts/{slug}/  # downloaded images, one folder per post
```

The `output/` directory is gitignored — copy the results into your Jekyll repo manually.

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.8+. See `requirements.txt` for pinned dependencies (`beautifulsoup4`, `markdownify`, `python-slugify`, `python-dateutil`, `requests`).

## Usage

Add one Wayback Machine URL per line to `urls.txt` (lines starting with `#` are ignored):

```
# https://web.archive.org/web/<timestamp>/https://example.com/some-post/
https://web.archive.org/web/20240412181457/https://kyleo.io/some-post/
```

Then run:

```bash
# Default: read urls.txt, auto-detect the source platform per URL
python index.py

# Use a different URL file
python index.py wuubi-urls.txt

# Force a platform instead of auto-detecting
python index.py wuubi-urls.txt --wordpress   # aliases: --yaaburnee, -p wp
python index.py urls.txt --ghost             # alias: -p gh
```

### Local HTML files (offline, no Wayback)

Any input line can be a path to a **locally saved HTML page** instead of a URL — useful when the Archive is flaky or the page is gone. Save it with your browser's *Save Page As → Web Page, Complete* (which produces `page.html` + a `page_files/` folder), then point the tool at the `.html`:

```bash
python index.py saved-pages.txt --wordpress   # one local .html path per line
```

Images are **copied** out of the sibling `page_files/` folder rather than downloaded. For a page from an unrecognized CMS, use the generic adapter:

```bash
python index.py saved-pages.txt --html        # alias for --platform generic
```

The generic adapter reads Open Graph / common title/date elements and pulls the body from `entry-content`/`post-content`/`article`/`main`. Pages with no real body (e.g. a homepage template) are skipped rather than written as empty posts.

### Moving posts into a Jekyll site

`to_jekyll.py` stages converted posts into a Jekyll repo's `_drafts/`, then promotes them into `_posts/` one at a time:

```bash
# Stage posts as _drafts/<slug>.md (+ a "wuubi" source tag, + their image assets)
python to_jekyll.py stage output/_posts/2018-*.md

# Send one straight to _posts/<date>-<slug>.md instead of _drafts/
python to_jekyll.py stage --to-posts output/_posts/2018-08-21-some-post.md

# Later, trickle a draft into _posts/ (date read from its front matter)
python to_jekyll.py promote some-post

# Or pick interactively from a listed menu of drafts
python to_jekyll.py menu
```

Override the target repo with `--repo PATH` and the injected tag with `--tag`.

### Guided wizard

`wizard.py` runs the whole pipeline interactively — pick a source (a `.txt` list, a folder of saved `.html`, or one URL/path), convert, then for each new post choose **draft / post / skip / leave**, and optionally open the promote menu:

```bash
python wizard.py
```

### Housekeeping

```bash
python index.py --clean   # delete everything under output/ (prompts; add -y to skip)
python index.py --prune   # drop stale output: older slug duplicates + orphaned asset folders
```

## Notes

- Inputs are **Wayback Machine URLs** or **local saved HTML files** — both expose the archived HTML structure (meta tags, theme classes) the adapters read. Live URLs work too if the page still matches the adapter's markup.
- Image downloads may fail for assets the Wayback Machine never crawled; the script warns and continues. It prefers the archive's raw-image (`im_`) capture and falls back to the original URL. (Local HTML inputs copy images from the `_files/` folder instead.)
- There are no tests or linters configured.
