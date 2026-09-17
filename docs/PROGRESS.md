# Progress Log

Update at the end of each working session.

## 2026-09-17 (later) — mockup and screenshots

**Done**

- **Site mockup, screenshotted.** `docs/screenshots/` has all seven page types in
  light, dark and at phone width. Everything in them is synthetic and every page
  says so — see the quarantine note below.
- **`scripts/make_mockup_data.py`** generates a seeded 24-month dataset (about
  48,000 operations across 5 carriers, 6 airports, 18 routes) in the BTS *source*
  column layout and pushes it through the real normalize → build → export path.
  The screenshots are therefore evidence the pipeline works end to end, not a
  drawing of what it might look like. It produced 101 pages with 0 drops.
- **M6 rule engine (`pipeline/summaries/rules.py`).** Eight deterministic rules
  producing the page summary: headline band, comparison against the route average,
  a better option if one exists, worst month, cancellations, how late when late,
  severe delays, and a small-sample caveat. 23 tests.
  This also **switches on the summary gate**, which had been reporting itself as
  skipped. Only the similarity gate remains unenforced.
- **"Comparison with alternatives"** — the PLAN.md §7 required block that was
  missing. Flight and route pages now carry every flight on the route, best
  on-time first, with the current page marked. It is a required block, so an empty
  one fails the gate.
- **Site design.** Header and nav, footer, home page with a client-side search
  (progressive enhancement: the full list renders without JavaScript), section
  indexes for routes/airports/airlines, and a connection-checker page.
- 132 tests passing.

**How the mockup avoids inventing data**

CLAUDE.md forbids placeholder statistics in pages. The resolution is containment:
synthetic data lives in `data/mockup/`, builds to `site/dist-mockup/`, and every
page carries a banner and is forced to `noindex` regardless of gate outcome. The
generator refuses to run against the real data root. Airport and carrier codes are
real because they are public facts; every number is invented and labelled.

**Next**

1. Still the same #1: **`make verify-source MONTH=2025-01`** from a machine that
   can reach BTS. Everything built so far is waiting on it.
2. M7 connection checker. The page exists but says "not computed yet" rather than
   showing an invented made-it rate. Needs MCT defaults per hub logged in
   DECISIONS.md.
3. M6's similarity check, the last unenforced gate.
4. M2: multi-year load, BTS lookup tables, and reproducing a published BTS figure.

**Open questions**

- Playwright is needed for `make screenshots` but is not in the declared stack, so
  it has not been added. Worth adding as a site devDependency?
- The flight page is long. Worth considering whether the delay-cause table earns
  its place above the fold on mobile.
- Airport pages compute an arrival/departure role split but the template only
  shows departures.

## 2026-09-17

**Done**

- **M0 complete.** `uv` project on Python 3.12, ruff + pytest configured, `.gitignore`
  covering `data/` and `.env`, GitHub Actions running lint and tests on push.
  Runtime dependencies are DuckDB alone — it reads CSV and writes Parquet natively,
  so no pandas or pyarrow, and downloads use `urllib`.
- **M1 code complete, verification outstanding.** Polite HTTP fetcher (throttled,
  conditional GET, descriptive UA), a BTS adapter that writes raw downloads once with
  a sidecar `.meta.json` (URL, sha256, bytes, fetch timestamp) and archives the old
  bytes when a month is revised, and a normalizer that produces canonical Parquet.
- **A verification gate that enforces the "verify before hardcoding" rule.**
  `verify-source` probes the candidate URLs, reads the real CSV header out of the zip,
  diffs it against the candidate mapping and records what it saw. `ingest` refuses to
  run without a matching record, and editing the schema invalidates the old one.
- **M3 complete.** Every metric expression is defined once and reused across flight,
  route, airport and airline views, so on-time % cannot mean different things on
  different pages. 17 views including month, day-of-week and departure-hour breakdowns.
- **M4 complete apart from the similarity gate.** Versioned page JSON, a gate runner
  producing publish/noindex/drop with every reason recorded, a CSV report and a
  manifest.
- **M5 first pass.** Astro site reading the exported JSON, one template covering all
  four page types, build-time inline SVG charts (light and dark, no client JS), a
  sitemap that excludes noindexed pages, and source credit plus data period on every page.
- **Docker stack.** Dashboard, Dagu as the local CI/CD server, DuckDB's web UI as a
  data viewer, an nginx server for the built site, and act for running the real GitHub
  workflow locally. `make up` starts it; the dashboard links to everything.
- 100 tests passing, including metric assertions against hand-computed numbers
  documented in `tests/fixtures/README.md`.

**Next**

1. **Run `make verify-source MONTH=2025-01` from a machine that can reach BTS.** Nothing
   downstream can be trusted until this passes; it will print a block to paste into
   DATA_NOTES.md. This is the single highest-value next action.
2. Resolve the reporting vs marketing carrier question (M1) and log the decision.
3. M2: load 36+ months, add the BTS lookup tables for airlines and airports, and
   reproduce a published BTS monthly on-time figure to validate the whole chain.
4. M6: the summary rule engine, which also switches on the two gates currently
   reporting themselves as skipped.

**Open questions**

- Reporting vs marketing carrier for flight identity — still open, and it decides what
  a "flight page" is.
- Brand name and domain.
- Airport pages currently compute both arrival and departure roles but the template
  shows departures. Decide whether the page should show both.
- The `act` image installs the latest release at build time. Pin `ACT_VERSION` once
  there is a known-good version.

**Verified this session**

- The Dagu container image is `ghcr.io/dagucloud/dagu` (not `dagu-org`), and current
  Dagu DAG syntax uses `steps: - id: … run: …` with `action: docker.run` for container
  steps. Checked against the project's own README rather than assumed.
- The `act` installer takes `-b <bindir>` and an optional version tag.
- Astro 5 builds the site and the templates render in light and dark at mobile width
  with no horizontal overflow (screenshotted).

**Could not verify (environment network policy)**

- `transtats.bts.gov` — denied, so the BTS URLs and column names remain candidates.
- `extensions.duckdb.org` — denied, so the DuckDB `ui` extension could not be loaded
  here. The viewer service downloads it on first start and caches it in a volume.
- No Docker daemon was available, so the compose stack is validated
  (`docker compose config` passes for every profile) but has not been run.

## 2026-09-15
- **Done:** Project plan, CLAUDE.md, data notes, and decision log created.
- **Next:** M0 repo foundation, then M1 source discovery.
- **Open questions:** reporting vs marketing carrier table; brand name and domain.
