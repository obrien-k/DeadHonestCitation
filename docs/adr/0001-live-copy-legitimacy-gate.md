# ADR-0001: A live copy earns a photo-record only through the legitimacy gate

- **Status:** Accepted
- **Date:** October 2026
- **PR:** obrien-k/DeadHonestCitation#15
- **Code:** `src/dead_honest_citation/core/legitimacy.py`, `core/pipeline.py`, `network/screenshot.py`
- **Related:** `docs/DESIGN.md` (provenance ladder)

## Context

The provenance ladder ranks `live` as "verifiable now, may rot". Verifiable *now* is the strongest thing a citation can offer, but only if the live URL still serves the article. Publishers redesign, and when they do, an old URL usually doesn't simply 404. It can:

- serve the CMS's "page not found" template with a `200` (a soft 404);
- 301 to the homepage, or walk a migration map of redirects;
- land on another domain entirely;
- belong to a lapsed domain that is now parked and for sale.

A citation that photographs any of those and stamps it `live` misrepresents its source.

The field test that prompted this: Chicago magazine's 2008 "Long Time Coming". The live URL 404s after a redesign, and the article may exist elsewhere on the site. Finding it is not DHC's job: walking a publisher's 301 map to locate a moved page is out of scope. But once a live copy *is* in hand, it is the best source there is, and the citation should carry proof that it was legitimate.

## Decision

**A live source cited by a citation target passes a legitimacy gate before it gets a photo-record.** `assess_live(url, resp, soup)` judges the response DHC already fetched, with no second request. It checks, in order:

1. **Status:** no 4xx/5xx on the final response.
2. **Redirect chain:** at most `MAX_REDIRECTS` (3) hops, so http→https, `www`, or a trailing slash all pass. The chain must stay on the same host (ignoring `www.`) and must not end on the homepage when a deeper path was requested.
3. **Soft 404:** the `<title>` or first `<h1>` isn't a not-found template.
4. **Parked domain:** no parking or marketplace fingerprints (`PARKING_MARKERS`: provider hosts and for-sale copy).
5. **CMS confirmed:** `detect_platform()` recognizes the page. The `generic` fallback doesn't count, because "some HTML came back" is not evidence of the publisher's article.

**Pass:** Playwright captures the final URL full-page (`<slug>-live.png`). The citation's `screenshot` points to the image, and its `note` reads `Live capture <date>: HTTP 200[, N redirect(s)], CMS: <platform>.` This is automatic; no flag is needed.

**Fail:** no photo-record, even with `--screenshot`, and the reason is printed. Conversion itself continues, because the cascade never dead-ends. The author's `--note` records what became of the live URL, and the archived capture remains the citation's anchor.

**The gate judges; it never searches.** It answers "is this URL the real page?" It doesn't follow trails to find where the page went.

Archived and local sources are unchanged. The gate doesn't apply, and `--screenshot` behaves as before.

## Rationale

- **Judge the bytes already fetched.** A second request could see a different redirect or a different page. The verdict describes the response the conversion actually used.
- **CMS detection as the identity check.** The adapters already encode what a real article page from a known platform looks like. Reusing `detect_platform()` makes the gate stricter as adapters improve, without a second fingerprint list.
- **Conservative host matching.** "Same host ignoring `www.`" rejects some legitimate moves (a `blog.` subdomain migration, for example). It's the right side to err on: a missed photo-record costs nothing the archived capture doesn't already cover, while a false one misrepresents the source.
- **Capture, don't crawl.** Chasing a publisher's redirect map is unbounded, site-specific work, and the result would be DHC's guess, not the publisher's page.

## Costs and open questions

- **Parked-domain detection is a fingerprint list.** New parking providers slip through until they're added.
- **The redirect cutoff (3) is a judgment call.** Revisit it if real publishers need more.
- **Soft-404 detection reads English copy only.**
- **The photo-record needs Playwright and a Chromium** (`.[screenshot]` + `playwright install chromium`). Without them the gate still runs and reports, but no image is taken.

## Evidence

`tests/test_legitimacy.py` runs the gate with real requests against a local HTTP server: a legitimate article and a one-hop same-site redirect pass. These fail, each with its reason: a 404, a redirect to the homepage, a 5-hop chain, a soft 404, a parked page, a page with no CMS, and an off-site redirect (127.0.0.1 → localhost).

`tests/test_browser.py` drives real Chromium through Playwright:
- a full-page and a cropped capture;
- a legitimate live copy getting its `-live.png` photo-record and note end to end;
- a parked page getting none even with `--screenshot`;
- a local source keeping the `--screenshot` behavior.
