# archive-2-md

Convert archived web pages — captured on the [Wayback Machine](https://web.archive.org/), saved to disk, or written in Word — into Markdown, deterministically and without rewriting the prose.

The tool is **platform-agnostic** on both ends. A registry of *input adapters* teaches it how to read each source CMS, theme, or format; five ship in the box — **Ghost**, **WordPress** (generalized across themes), a **generic** HTML adapter for unknown CMSes, **Word `.docx`**, and **ProBoards** forum threads. A symmetric registry of *output targets* decides how results are written — **Jekyll** ([kramdown](https://kramdown.gettalong.org/)-friendly front matter, the default), **CommonMark**, or a **data** target that emits provenance-stamped citation objects. Adding either end is a single registry entry.

> **DeadHonestCitation** started life as `ghost-2-md`, a Ghost-only exporter, and grew into a general archive→Markdown converter with provenance-stamped citations.

## What it does

For each source it:

- Loads the page — fetching from the Wayback Machine (with retry/back-off on rate limits), reading a saved `.html` file, or converting a `.docx`
- Strips the Wayback Machine toolbar injected into archived pages
- **Auto-detects the source platform** from the markup (or you can force one)
- Extracts title, date, description, tags, categories, and cover image via the platform's adapter
- Locates the article body via the adapter's content selector (falling back to `<article>`/`<main>`)
- Runs the adapter's cleanup pipeline (e.g. drops Ghost/Koenig CSS classes, WordPress share bars and related-post blocks)
- Converts embeds (YouTube/Vimeo → labeled links), drops Flash/ad junk, and flags anything that needs a human with a `⚠ NEEDS REVIEW` note instead of dropping it silently
- Downloads and localizes every image, rewriting `src` to a repo-relative asset path
- Converts footnotes to native Markdown `[^1]` syntax (kramdown-compatible)
- Converts HTML → Markdown (headings, links, tables, code blocks) and escapes `|` so kramdown won't misread link text as a table
- Writes the result through the chosen output target (Jekyll post, CommonMark file, or a citation object)

Forum threads use a *thread* content model: each post is preserved as an attributed `**author** — date` block with the message as a blockquote, rather than flattened into one article. Loose `.md`/`.txt` files pass through verbatim (no HTML round-trip). Re-runs are idempotent — outputs that already exist are skipped.

## The pieces

| Script | Role |
|--------|------|
| `index.py` | The converter. Reads sources → writes Markdown into `output/`. |
| `discover.py` | Finds Wayback URLs without knowing them up front: enumerate a domain, recover an unknown host from a remembered name, or Save Page Now a live URL. |
| `to_jekyll.py` | Stages converted posts into a Jekyll repo's `_drafts/` and promotes them into `_posts/`. |
| `wizard.py` | Guided, interactive flow that ties the above together. |

## Architecture

The converter, `index.py`, is built around a **platform adapter registry** (`PLATFORMS`). Each adapter supplies four pieces, so supporting a new CMS/theme/format means adding one entry plus its functions — no changes to the processing pipeline:

| Piece | Responsibility |
|-------|----------------|
| `detect(soup)` | Recognize the platform from page markup (drives auto-detection) |
| `extract_metadata(soup)` | Return `(title, date, description, tags, cover, categories)` |
| `content` | A `(tag_name, attrs)` selector — or a list tried in order — locating the article body |
| `clean(article)` | Platform-specific body-cleanup pipeline |

The pipeline in `process_url()` is platform-neutral — it calls into the resolved adapter at each step:

1. `load_source()` — fetch a URL (with retry), read a saved `.html`, or convert a `.docx`
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

### The input layer

`collect_sources()` resolves the positional CLI tokens into a flat, de-duplicated work list, classifying each one independently so a single run can mix kinds:

| Token | Becomes |
|-------|---------|
| a directory | every source file inside (recurse with `--recursive`) |
| an `http(s)` URL | itself |
| a `.html`/`.htm`/`.docx` path | that one saved page or Word doc |
| a `.md`/`.markdown` path | a Markdown passthrough (also `.txt` under `--txt`) |
| any other existing file | a *list file* — one source per non-blank, non-`#` line (the classic `urls.txt`; `.txt` stays a list file unless `--txt`) |

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

The `output/` directory is gitignored — use `to_jekyll.py` (below) or copy the results into your Jekyll repo manually.

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.8+. See `requirements.txt` for pinned dependencies (`beautifulsoup4`, `markdownify`, `python-slugify`, `python-dateutil`, `requests`, and `mammoth` for `.docx`).

## Usage

Sources are positional and can be mixed in one run. The default, with no arguments, reads `urls.txt`. A starter `urls.example.txt` shows the format — copy it to `urls.txt` (gitignored) and edit, or pass any path:

```bash
# Default: read urls.txt, auto-detect the source platform per source
python index.py

# A list file, a saved page + a live URL, or a whole directory
python index.py urls.example.txt
python index.py page.html https://example.com/post
python index.py ./saved-pages/                 # every .html/.htm/.docx inside
python index.py ./saved-pages/ --recursive     # descend into subdirectories

# Force a platform instead of auto-detecting
python index.py urls.example.txt --wordpress   # aliases: --yaaburnee, -p wp
python index.py urls.txt --ghost               # alias: -p gh
```

### Discovering archived URLs

If you don't already have the URLs, `discover.py` has three modes.

**Enumerate a known domain** — prints captures in the format `index.py` consumes:

```bash
python discover.py example.com                  # every archived HTML page
python discover.py example.com --contains foo   # only URLs whose slug contains "foo"
python discover.py example.com -o urls.txt      # write a source list
python discover.py example.com --newest         # each URL's most recent capture
```

> CDX (the Wayback index) exposes the captured **URL**, not the page `<title>`, so `--contains` matches the slug. For Ghost/WordPress the slug is usually derived from the title, so a title word is normally present — but a post that was never crawled (e.g. a draft) won't appear at all.

**Recover an unknown host** from a remembered *name* — probes common hosting platforms (and any `--on DOMAIN`) and reports which candidates are archived and/or live:

```bash
python discover.py --recover myoldforum               # try myoldforum.proboards.com, .blogspot.com, …
python discover.py --recover myblog --on example.com  # also try myblog.example.com
```

**Save Page Now** — archive a live-but-unarchived URL and print its new permalink (turns a `live` source into an `archived` one):

```bash
python discover.py --save https://example.com/page/
```

### Local HTML files (offline, no Wayback)

Any source can be a path to a **locally saved HTML page** instead of a URL — useful when the Archive is flaky or the page is gone. Save it with your browser's *Save Page As → Web Page, Complete* (which produces `page.html` + a `page_files/` folder), then point the tool at the `.html`:

```bash
python index.py saved-pages.txt --wordpress    # one local .html path per line
```

Images are **copied** out of the sibling `page_files/` folder rather than downloaded. For a page from an unrecognized CMS, use the generic adapter:

```bash
python index.py saved-pages.txt --html         # alias for --platform generic
```

The generic adapter reads Open Graph / common title/date elements and pulls the body from `entry-content`/`post-content`/`article`/`main`. Pages with no real body (e.g. a homepage template) are skipped rather than written as empty posts.

### Word documents

Point the tool at a `.docx` (or a directory of them). It's converted to HTML up front, embedded images are extracted, and title/author/date are read from the document's metadata:

```bash
python index.py draft.docx                      # auto-detected; or force with --docx / --word
```

### Markdown / plain-text passthrough

Loose `.md`/`.markdown` files are brought in verbatim (no HTML round-trip): the body is kept as-is and title/date/tags are lifted from a leading YAML front-matter block if present, else the first heading or the filename. A `.txt` file stays a *list file* by default (so `urls.txt` keeps working) — pass `--txt` to treat `.txt` inputs as Markdown content instead:

```bash
python index.py notes.md                        # .md is always passthrough
python index.py old-post.txt --txt              # treat .txt as content, not a list file
```

### Output formats

`--target` selects how results are written (default `jekyll`):

```bash
python index.py urls.txt                         # jekyll posts (default)
python index.py urls.txt --target commonmark     # plain CommonMark + minimal front matter
python index.py urls.txt --target data           # provenance-stamped citation objects
```

The **`data`** target writes each source as a citation rather than a post:

- `_data/sources/<id>.yml` — the citation record (id = title slug = cite key)
- `_sources/<id>.md` — the extracted content
- `_includes/cite.html` — a plugin-free Jekyll include, shipped once

Each record carries **honest provenance**: `archived` (a Wayback permalink + snapshot date), `live` (URL + access date), or `local` (a saved file — never claims a public link). Cite it in a document with `{% include cite.html id="some-slug" %}`. Add `--screenshot` to render each page to a PNG and reference it from the citation (optional; needs `playwright` — `pip install playwright && playwright install chromium`). See [`docs/DESIGN.md`](docs/DESIGN.md) for the citation object and the rest of the direction.

A source that isn't convertible HTML — a PDF, image, or other binary — is **captured verbatim** (saved as an asset, recorded with a reference) rather than dropped, so a run preserves everything it touches. Each source's outcome (converted / captured / skipped / failed) is appended to `output/runlog.jsonl`.

### Moving posts into a Jekyll site

`to_jekyll.py` stages converted posts into a Jekyll repo's `_drafts/`, then promotes them into `_posts/` one at a time:

```bash
# Stage posts as _drafts/<slug>.md (+ a source tag, + their image assets)
python to_jekyll.py stage output/_posts/2018-*.md

# Send one straight to _posts/<date>-<slug>.md instead of _drafts/
python to_jekyll.py stage --to-posts output/_posts/2018-08-21-some-post.md

# Later, trickle a draft into _posts/ (date read from its front matter)
python to_jekyll.py promote some-post

# Or pick interactively from a listed menu of drafts
python to_jekyll.py menu
```

The target repo and injected source tag default from the environment — set
`DHC_JEKYLL_REPO` and `DHC_SOURCE_TAG`, or copy `.env.example` to
`.env` (gitignored) and fill it in. `--repo PATH` and `--tag` override per run.

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

## Development

Linting and formatting use [Ruff](https://docs.astral.sh/ruff/):

```bash
pip install ruff
ruff check .       # lint
ruff format .      # format
```

Configuration lives in `pyproject.toml`. There are no automated tests yet.

## Notes

- Inputs are **Wayback Machine URLs**, **local saved HTML files**, **Word `.docx`**, or loose **Markdown/`.txt`** — the HTML kinds expose the structure (meta tags, theme classes) the adapters read. Live URLs work too if the page still matches an adapter's markup.
- Image downloads may fail for assets the Wayback Machine never crawled; the script warns and continues. It prefers the archive's raw-image (`im_`) capture and falls back to the original URL. (Local HTML inputs copy images from the `_files/` folder instead.)
