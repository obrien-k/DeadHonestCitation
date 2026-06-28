# DeadHonestCitation — design

## Purpose

DeadHonestCitation turns archived and locally-saved web sources into
**provenance-stamped, citable evidence**. It ingests a heterogeneous corpus — blogs,
forums, static sites, never-archived personal copies, Word `.docx`, loose `.txt` —
and emits, for each source, a citation that is honest about how verifiable it is:
publicly checkable on the Wayback Machine, live today, or only an author's personal
copy. **Veracity is the product:** it makes a claim's sources traceable and never
overstates how verifiable a source is.

## Core concept: the Citation Object

One flat record per source — the spine everything else populates.

```yaml
id:          geocities-myfirstsite      # stable slug, the citation key
title:       "My First Site (1999)"
kind:        page | post | thread | document | image   # routed from mimetype/adapter
provenance:  archived | live | local
source_url:  http://www.geocities.com/...
archive_url: https://web.archive.org/web/1999.../http://...   # when archived
captured_at: 1999-08-12                 # snapshot ts (archived) or access date (live)
screenshot:  assets/img/sources/geocities-myfirstsite.png
content:     _sources/geocities-myfirstsite.md          # extracted text, or null
note:        "optional author caption"
```

### Provenance ladder (the honesty feature — a rung must never lie)

| Level | Means | Cited as |
|---|---|---|
| `archived` | public Wayback capture | permalink + timestamp — anyone can verify |
| `live` | still online today | URL + access-date — verifiable now, may rot |
| `local` | only a personal saved copy, never/not-yet archived | "author's personal copy" — author attests |

A `local` copy also found on Wayback upgrades to `archived`. A `live` source can be
pushed to `archived` via **Save Page Now** to mint a real permalink before it rots.

## Pipeline

`ingest → fetch (capture raw + screenshot) → try-convert → emit citation object → embed by id`

- **Capture tier (floor, format-agnostic):** pull raw bytes of everything; every source
  is handled here regardless of type. Guarantees completeness.
- **Convert tier (best-effort enrichment):** HTML matching a known/generic adapter →
  Markdown. Unmatched sources stay capture-only and are still cited.
- **Invariant:** every source ends in exactly one terminal state — `converted`,
  `captured`(-raw), or `failed` — and each is recorded, never silent.

## Registries (the two pluggable seams)

- **Input adapters** (existing `PLATFORMS`): `detect / extract_metadata / content /
  clean`. Content models: *article* (blog) and *thread* (forum — preserve per-post
  author·date·body rather than flattening). Targets: ghost, wordpress, generic, docx,
  **txt** (trivial passthrough), **proboards** (forum; keys on `windowbg`/`windowbg2`
  rows, `action=viewprofile&user=` authors, `titlebg`/`cattext` title).
- **Output targets** (new, symmetric registry): each decides front matter +
  filename/layout + md flavor + asset path. `jekyll` (default, back-compat) ·
  `commonmark`/`plain` · `hugo` · `data` (emits the Citation Object). The conversion
  core stays target-agnostic — it produces `(metadata, body, assets)`.

## Discovery

- **Known domain** → `discover.py` CDX enumeration (works today).
- **Fuzzy / unknown host** → recover the host via web search first, then CDX. (CDX
  can't guess a host; the reversed urlkey and unknown numbered domains defeat prefix
  match.)
- **Live but unarchived** → optionally Save-Page-Now to create an archive link.

## State (no database)

The filesystem is the ledger (an existing `.md`/asset = done). Add one append-only
**JSONL run-log** for nuanced outcomes (failed / captured-raw / snapshot / attempts):
a log, not a DB; derivable from the filesystem; single-writer under concurrency.

## Fetch policy

Resilient and polite: global rate limit, honor `Retry-After`, exponential backoff,
bounded concurrency, identifiable client. Survive interruption by backing off and
resuming, never by pushing through blocks.

## Decisions

- **Citation embedding — A: cite-by-`id` into a `_data/sources/` collection.** Single
  source of truth for provenance; the tool stays out of authored prose (writes only
  its own `_data/sources/` namespace). Rendered by a **plugin-free include**
  (`{% include cite.html id="..." %}`), not a custom Liquid tag — so it builds on stock
  GitHub Pages. Per output target: Jekyll include, Hugo `{{< cite "id" >}}` shortcode,
  both reading the SSG's data dir. Prior art: jekyll-scholar (BibTeX, plugin); ours is
  lighter and web-source-oriented.

## Build sequence

1. This design doc ✅
2. **Output-target registry** — Jekyll/kramdown emit tail factored out; `jekyll`
   default (back-compat). ✅
3. **Citation Object** as the `data` target (`_data/sources/<id>.yml` + `cite` include). ✅
4. **ProBoards adapter** + the *thread* content model. ✅
5. **txt** passthrough adapter. ✅
6. Discovery host-recovery + Save-Page-Now (`discover.py`). ✅
7. Capture tier (binary/non-HTML capture) + screenshots (optional playwright). ✅
8. Polite-fetch layer (`netpolite.py`: rate limit / Retry-After / backoff) + JSONL
   run-log. ✅ (Sequential, so concurrency is bounded at 1.)

### Possible next

- Raw-HTML capture when no adapter matches (today: logged as `failed`, asks for
  `--platform`).
- Resume / retry-failed driven by the run-log.
- `local`→`archived` upgrade and Save-Page-Now wired into the convert flow.
