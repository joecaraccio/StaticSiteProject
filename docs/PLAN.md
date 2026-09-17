# Usually Late: Project Plan

Status: draft v1 · Owner: Joe · Working name is a placeholder until domain and trademark checks are done.

## 1. Goal

Help U.S. travelers choose a flight by showing how reliable each flight, route, airport, and airline has been historically. Answer questions like:

- "Is this flight usually late?"
- "Which flight on this route should I book if I need to arrive on time?"
- "Will I make a 55-minute connection at O'Hare?"
- "When are delays worst at my airport?"

- Additionally consider press tracking

Live tracking ("where is my plane right now?") is out of scope for initial gen. That market is owned by large incumbents with real-time data.

## 2. Success criteria

- **v1 launch:** 500–1,000 high-quality pages live, all passing quality gates, sitemaps submitted, data refreshed monthly without manual steps.
- **Month 4 checkpoint:** a majority of submitted pages indexed by Google. If most sit at "crawled, not indexed," improve templates before adding more pages.
- **Month 6 checkpoint:** impressions growing week over week and at least one page type earning clicks.
- **Month 12 target:** 10K–50K monthly visits and first revenue.

## 3. Scope

### In v1

- Monthly ingest of BTS on-time performance data, several years of history
- Flight, route, airport, and airline pages
- Rule-based summaries and quality gates
- Static site with inline SVG charts, sitemaps, and source attribution
- Connection checker for a limited set of major hubs
- Placeholder components for ads, affiliate modules, and email signup (off by default)

### Later (not v1)

- Airline consumer scorecards from the Air Travel Consumer Report
- Airport checkpoint timing from TSA hourly throughput reports
- Route and network explorer from T-100 traffic data
- Paid tier ("Trip Watch"), team reports, derived-data API
- Airfare history from the DB1B ticket sample

### Non-goals


- Language-model-generated page text
- International flights (source data covers U.S. domestic operations)

## 4. Architecture

```
BTS downloads ──► sources/ (adapters) ──► data/raw/  (immutable, checksummed)
                                              │
                                              ▼
                                  normalize + validate
                                              │
                                              ▼
                              data/clean/*.parquet  +  DuckDB views
                                              │
                                              ▼
                        metrics/ ──► export/ (page JSON) ──► gates/
                                                               │
                                          publish / noindex / drop
                                                               │
                                                               ▼
                                              site/ (Astro static build)
                                                               │
                                                               ▼
                                                 static host + sitemaps
```

### Key design choices (log changes in DECISIONS.md)

- **DuckDB + Parquet:** analytical queries over tens of millions of rows on a laptop, no server.
- **Static site:** cheap, fast, and simple. Check the host's per-deploy file limits before generating tens of thousands of pages. If the limit is a problem, options are page waves, a different host, or on-demand rendering with cached JSON.
- **Page JSON contract:** the site never queries the database. The pipeline writes one JSON file per page conforming to a versioned schema, which keeps the site dumb and testable.
- **Rule-based summaries:** deterministic, testable, and accurate.

## 5. Data model (canonical)

Details and source field mappings go in `DATA_NOTES.md`.

### Entities

| Table | Key | Notes |
|---|---|---|
| `airlines` | carrier code + BTS unique carrier ID | Carrier codes can be reused over time; use BTS unique IDs for identity |
| `airports` | IATA code + BTS airport ID | Name, city, state, time zone |
| `flights` | carrier + flight number + origin + dest | Derived from operations; track first/last seen dates |
| `routes` | origin + dest | Derived |

### Events

`operations`: one row per scheduled flight.

| Field | Meaning |
|---|---|
| `flight_date` | Local date of scheduled departure |
| `carrier`, `flight_number`, `origin`, `dest` | Identity |
| `sched_dep`, `actual_dep`, `sched_arr`, `actual_arr` | Local times as reported |
| `dep_delay_min`, `arr_delay_min` | As reported |
| `arr_del15` | BTS 15-minute arrival delay flag |
| `cancelled`, `cancellation_code`, `diverted` | Status |
| `carrier_delay`, `weather_delay`, `nas_delay`, `security_delay`, `late_aircraft_delay` | Delay cause minutes (populated only for qualifying delays) |
| `distance` | Miles |
| `source_file`, `ingested_at` | Lineage |

## 6. Metrics

Defined once in `pipeline/metrics/` and tested against hand-computed fixtures.

- On-time % (see CLAUDE.md definition)
- Cancellation %, diversion %
- Average arrival delay when late (arrival delay ≥ 15 minutes)
- Share of flights 3+ hours late
- Delay distribution buckets: on time, 15–30, 30–60, 60–120, 120–180, 180+, cancelled/diverted
- Delay cause shares by minutes
- On-time % by month of year, day of week, and scheduled departure hour
- Trend: trailing 3 months vs prior-year same months
- Route and airport baselines for comparisons ("17 points below the morning average on this route")

## 7. Page types

| Page | URL pattern | Gate: publish if | Otherwise |
|---|---|---|---|
| Flight | `/flights/{carrier}/{number}/{origin}-{dest}` | ≥30 operations in trailing 12 months | `noindex` if 10–29; `drop` below 10. If not seen for 180+ days: `noindex` and link to route page |
| Route | `/routes/{origin}-{dest}` | ≥60 operations in trailing 12 months | `drop` |
| Airport | `/airports/{code}` | ≥500 operations in trailing 12 months | `noindex` |
| Airline | `/airlines/{code}` | Always, for reporting carriers | — |
| Monthly list | `/airports/{code}/least-reliable/{yyyy-mm}` | Airport page is published | — |
| Connection checker | `/connections` (tool) | Precomputed pairs only for selected hubs | — |

Thresholds are starting points. Record any change in DECISIONS.md.

### Additional gates for all pages

- All required blocks rendered with real data
- At least one summary rule matched
- Text similarity to sibling pages ≤ 0.90 (else `noindex`)
- Data age within expected refresh window

### Required page elements

Title matching search phrasing, data period, source credit, rule-based summary, headline stats, month-by-month chart, delay-cause breakdown, delay distribution, comparison with alternatives, related links, last-updated date.

## 8. Connection checker (v1 model)

- For a pair (inbound flight A to hub H, outbound flight B from H), find dates where both were scheduled.
- A connection is **made** if A's actual arrival + minimum connection time ≤ B's actual departure, and B operated.
- Treat A cancelled/diverted as a miss. If B was cancelled, record it separately (the traveler would be rebooked regardless).
- Minimum connection time: configurable default per airport (for example, 45 minutes domestic). There is no public source for official MCTs, so label the assumption on the page.
- Only report pairs with ≥30 co-scheduled days. Show the sample size.
- v1 covers a handful of major hubs, precomputed to JSON; the page does lookups client-side.

## 9. SEO and quality

- Sitemap index with one sitemap per page type, each ≤50,000 URLs
- Canonical URLs, clean titles and meta descriptions
- Internal links: flight ↔ route ↔ airport ↔ airline
- Launch in waves: best 500–1,000 pages first, then expand as indexing proves out
- Google Search Console set up before launch; track indexed vs submitted by page type
- Avoid thin or near-duplicate pages; this is why the gates exist

## 10. Monetization hooks (v1: interfaces only)

- `AdSlot` component, disabled by default
- `AffiliateModule` component with typed props (travel cards, insurance, airport hotels, parking), disabled by default
- `EmailSignup` component posting to a provider chosen later
- No tracking beyond privacy-friendly analytics in v1

## 11. Milestones

Check tasks off here as they're completed.

> Status note (2026-09-17): M0, M3 and M4 are complete, and M6's rule engine is
> done (the similarity check is not). M1's code is written and tested but the
> source is **not verified** — see docs/DATA_NOTES.md. M5 renders every page type;
> screenshots of all of them are in docs/screenshots/, captured from a synthetic
> mockup build. Boxes below are ticked only for work that is done.

### M0 · Repo foundation
- [x] Initialize repo, `uv` project, `ruff`, `pytest`, `.gitignore` (including `data/`, `.env`)
- [x] GitHub Actions: lint + tests on push
- [x] Create `docs/DECISIONS.md` and `docs/PROGRESS.md`
- **Done when:** CI passes on an empty test suite and the layout matches CLAUDE.md.

### M1 · Source discovery and single-month ingest
- [ ] Find and document the current BTS download method for on-time data (see DATA_NOTES.md checklist)
- [ ] Resolve the reporting vs marketing carrier question and log the decision
- [x] Source adapter: download one month, save raw with checksum and timestamp, skip unchanged files
- [x] Parse to Parquet with explicit column types
- [ ] Record the verified schema in DATA_NOTES.md
- **Done when:** one month loads reproducibly and row count matches the source.
- *Blocked:* verification needs network access to transtats.bts.gov. The adapter, the verifier and the ingest gate are written and tested; run `make verify-source MONTH=YYYY-MM` to finish this milestone.

### M2 · Multi-year load and validation
- [ ] Load 36+ months
- [ ] Load BTS lookup tables for airlines and airports
- [ ] Validation checks: row counts vs prior year, value ranges, required fields, duplicate detection
- [ ] Reproduce a published BTS monthly on-time figure within a small tolerance and document the method
- **Done when:** validation report is clean and the BTS comparison matches.

### M3 · Metrics layer
- [x] Implement metrics from section 6 as DuckDB views or functions
- [x] Hand-computed fixture tests for each metric, including edge cases (all cancelled, no delays, small samples)
- **Done when:** metrics tests pass and a sample route's numbers are spot-checked by hand.

### M4 · Page export and gates
- [x] Versioned JSON schema for each page type
- [x] Export page JSON for all candidate pages
- [x] Gate runner producing `publish` / `noindex` / `drop` plus a CSV report with reasons
- **Done when:** gate report shows counts per page type and reasons, and exported JSON validates against the schema.

### M5 · Site v1
- [x] Astro project reading page JSON
- [x] Templates: flight, route, airport, airline
- [x] Build-time SVG charts; responsive, light/dark theme, accessible
- [x] Sitemaps, canonical tags, robots rules for `noindex` pages
- [x] Source credit and data period on every page
- **Done when:** local build renders all published pages and passes a Lighthouse check.

### M6 · Summaries and similarity gate
- [x] Rule engine in `pipeline/summaries/` (Python rules, not YAML — see DECISIONS.md)
- [x] Tests covering each rule
- [ ] Similarity check against sibling pages feeding the gate runner (the gate is wired and reports itself as skipped until this lands)
- **Done when:** a random sample of 50 pages reads naturally and varies meaningfully.

### M7 · Connection checker
- [ ] Choose initial hubs and MCT defaults; log in DECISIONS.md
- [ ] Precompute pair results with sample sizes
- [ ] Client-side tool page
- **Done when:** results for a few pairs are verified by hand from raw data.

### M8 · Launch wave 1
- [ ] Choose domain and brand; check trademark conflicts
- [ ] Deploy to static host; confirm file limits
- [ ] Search Console and analytics set up; submit sitemaps
- [ ] Scheduled monthly refresh job in CI with failure alerts (runs locally today via the Dagu `refresh` DAG; needs a hosted equivalent)
- **Done when:** first wave is live and the monthly job has run once end to end.

### M9+ · Later
- Airline scorecards (Air Travel Consumer Report)
- Airport checkpoint timing (TSA weekly hourly throughput PDFs)
- Route explorer (T-100)
- Paid tier, team reports, derived-data API

## 12. Risks

| Risk | Mitigation |
|---|---|
| Source format or URL changes | Adapters pause and alert on schema change; raw files are kept |
| Flight renumbering breaks pages | Track first/last seen; `noindex` stale flights and link to route pages |
| Google treats pages as thin | Gates, similarity checks, launch in waves, monitor indexing |
| Small samples mislead users | Minimum sample sizes; always show sample size |
| Monthly data lag | State data period clearly; position as historical planning data |
| Host file limits | Check before M8; waves or alternate rendering |
| Employer IP concerns | Personal equipment and time only; nothing from work |

## 13. Open questions

- Reporting carrier vs marketing carrier table for flight identity (see DATA_NOTES.md)
- How to handle codeshare flight numbers travelers search for
- MCT defaults per hub
- Final brand name and domain
- Hosting choice after file-limit check
- Analytics provider
