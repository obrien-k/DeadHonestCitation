README.md# Ghost Archive Migrator (v1.0)

Deterministic migration tool for converting archived Ghost blog posts
(from Wayback Machine) into Jekyll-compatible Markdown posts.

## Features

- Extracts title, publish date, tags
- Converts HTML → Markdown
- Converts Ghost footnotes to native Markdown footnotes
- Downloads images locally
- Removes Ghost-specific classes
- Normalizes duplicate H1 tags
- Converts tables to Markdown
- Preserves content fidelity (no text edits)

## Usage

1. Create `urls.txt` with one Wayback URL per line.
2. Activate virtual environment.
3. Run: python index.py

Output is written to:

```
output/_posts/
output/assets/img/blog/posts/
```

## Version

v1.0 — Stable manual URL migration
