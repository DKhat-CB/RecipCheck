# RecipCheck — Membership Reciprocity Optimizer (Phase 1)

Tells a family the cheapest cultural-institution membership (or pair) that covers the
museums, zoos, science centers, and gardens they actually visit, by exploiting the
**reciprocal-admission programs** those institutions belong to (NARM, ROAM, MARP, ASTC,
AZA, AHS, ACM, Time Travelers).

**Phase 1 scope: Bay Area and NYC only.**

The user gives family makeup (ages), home ZIP, typical extra guests, and up to five target
institutions with intended visits/year. The tool returns the best home membership to buy,
what it covers, what it cannot cover and why (the counterintuitive **90-mile rule**), and
estimated annual savings versus paying per visit.

## How it works

A four-stage pipeline. Stages 1–2 produce a versioned dataset; stages 3–4 consume it and
run fully client-side in the browser.

1. **Roster ingestion (Tier 1)** — `scraper/rosters.py`: which institution belongs to which
   reciprocal program.
2. **Membership-page extraction (Tier 2)** — `scraper/membership_pages.py` +
   `scraper/extract.py`: crawl each institution's own membership page and extract tiers,
   prices, guest allowances, child age thresholds, and general-admission prices via a narrow
   Gemini call with schema-enforced JSON output. Cached and hashed so re-scraping is cheap.
3. **Optimizer** — `optimizer/` (Python reference) and `web/app.js` (client-side): generate
   candidate memberships, check coverage against the distance rules and per-tier eligibility,
   pick the cheapest covering set.
4. **Interface** — `web/index.html`: static single-page app reading a compiled
   `web/dataset.json`.

## Repo layout

```
data/
  programs.json          # hand-authored program-level rules (stable)
  institutions/          # pipeline output, per metro
    bay_area.json
    nyc.json
  raw_cache/             # gitignored raw HTML + hash sidecars
  review_queue.json      # low-confidence / blocked records for human review
  zcta_centroids.csv     # ZIP -> lat/lng (US Census Gazetteer, two-metro subset)
scraper/
  geocode.py             # haversine + Nominatim wrapper
  rosters.py             # Tier 1 ingestion
  membership_pages.py    # Tier 2 crawl (httpx -> Playwright fallback)
  extract.py             # Gemini extraction wrapper (Pydantic schema)
  orchestrate.py         # caching, hashing, politeness, scheduling
  validate.py            # cross-checks, confidence routing
optimizer/
  rules.py               # 90-mile, tier sizing, guest/age, reciprocity logic
  model.py               # candidate gen, coverage, objectives, savings
  tests/                 # pytest suite + shared JS/Python fixture
web/
  index.html
  app.js                 # client-side optimizer + UI
  styles.css
  dataset.json           # compiled from data/institutions/
config.yaml
```

## Setup

```bash
pip install -r requirements.txt
# Gemini key (free tier) — required only to (re)run the scraper, not the optimizer/UI:
echo 'GEMINI_API_KEY=your-key' > .env        # .env is gitignored
```

Chromium for the Playwright fetch fallback is expected at `PLAYWRIGHT_BROWSERS_PATH`
(already present in the managed environment); otherwise run `playwright install chromium`.

## Running

```bash
# Scraper pipeline (produces data/institutions/*.json + data/review_queue.json)
python -m scraper.orchestrate --metro bay_area
python -m scraper.orchestrate --metro nyc

# Compile the browser dataset
python -m scraper.orchestrate --compile

# Optimizer tests
python -m pytest optimizer/tests -q

# Interface (static — any file server works)
python -m http.server -d web 8000   # then open http://localhost:8000
```

## Why a scraper plus an LLM

The reciprocal-program rosters are semi-centralized but ugly, and the part nobody publishes
cleanly — which membership *tier* unlocks reciprocity and what it costs — lives on each
institution's own page in bespoke HTML that changes roughly yearly. The pipeline is a
**deterministic** crawler/cacher with a **narrow** LLM extraction step (schema-enforced, no
free-form output) so the dataset stays trustworthy and cheap to refresh.

See `data/review_queue.json` for records the pipeline could not extract with high confidence
(WAF-blocked, JS-only, or ambiguous pages); these are resolved by hand to reach a trustworthy
first dataset. Maintenance cadence and known edge cases are documented at the bottom of this
file.

## Known edge cases encoded

- **Non-participating marquee institutions** (e.g. Cal Academy, Exploratorium have
  historically not offered reciprocity) → flagged `non_participating`; evaluated on their own
  membership economics.
- **50%-only programs** (AZA, ACM) → `reciprocity_type` `fifty_percent`; treated as partial,
  surfaced in savings but not full coverage under must-cover-all.
- **ASTC 90-mile rule** — linear radius from *both* residence and home institution.
- **Reciprocity rides on higher tiers** — per-tier program mapping is mandatory.
- **Annual card window** — visits spanning >12 months can break single-card coverage.
- **Closures/relocations** → flagged `possibly_closed` rather than emitting confident stale data.

## Maintenance

- **Full re-scrape quarterly** (memberships reprice roughly yearly). Unchanged
  membership-section hashes skip the Gemini call, so re-scrapes are cheap.
- **On-demand refresh** when an optimizer query touches a record whose `last_verified` is
  older than `maintenance.stale_after_days` (default 120); such records are flagged `stale`.
- **Versioning/rollback** — dataset files live in git; each compile is a commit; rollback is
  `git revert`.

## Non-goals (Phase 1)

Amusement-park/Herschend passes, America-the-Beautiful national-parks pass, international
institutions, driving-distance routing, user accounts/auth, payments, and any metro beyond
Bay Area and NYC.
