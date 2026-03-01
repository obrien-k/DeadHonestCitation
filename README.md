# ghost-2-md

Convert archived Ghost posts (via Wayback Machine) into Jekyll-compatible Markdown — deterministically, without touching the text.

## What it does

- Fetches archived Ghost posts from Wayback Machine URLs
- Extracts title, date, description, tags, and cover image from meta tags
- Converts HTML → Markdown (headings, links, tables, code blocks)
- Converts Ghost footnotes → native Markdown footnote syntax `[^1]`
- Downloads and localizes all post images
- Strips Ghost/Koenig CSS classes and Wayback toolbar injection
- Normalizes duplicate `<h1>` tags inside article bodies
- Skips already-processed posts (safe to re-run)
- Retries failed Wayback Machine fetches automatically

## Output

```
output/
  _posts/         # YYYY-MM-DD-slug.md files, ready for Jekyll
  assets/img/posts/  # Downloaded images, organized by post slug
```

## Setup

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

1. Add one Wayback Machine URL per line to `urls.txt`:

```
# Lines starting with # are ignored
https://web.archive.org/web/20240412181457/https://kyleo.io/some-post/
https://web.archive.org/web/20230101000000/https://kyleo.io/another-post/
```

2. Run:

```bash
python index.py
```

Or pass a different URL file as an argument:

```bash
python index.py my-other-urls.txt
```

## Notes

- Use Wayback Machine URLs, not live Ghost URLs — the script expects Ghost's HTML structure and Open Graph meta tags as archived
- Image downloads may fail for URLs that were never crawled by the Wayback Machine; the script will warn and continue
- The `output/` directory is gitignored by default — copy results into your Jekyll repo manually

## Requirements

Python 3.8+. See `requirements.txt` for pinned dependencies.
