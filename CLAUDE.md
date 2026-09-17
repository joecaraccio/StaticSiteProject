# CLAUDE.md

Context for Claude Code working in this repository. Read this file and `docs/PLAN.md` at the start of every session.

## What this project is

A flight reliability website (working name **Usually Late**) that helps U.S. travelers decide *which flight to book* using public U.S. DOT on-time performance data. It is a planning tool first, not focused on live flight tracking. 

The system has four parts:

1. **Pipeline** – downloads public BTS data, stores raw files untouched, and normalizes them into Parquet/DuckDB.
2. **Metrics layer** – SQL views that compute reliability stats (on-time %, cancellation %, delay distribution, delay causes, seasonality).
3. **Page generator** – exports one JSON document per page, runs quality gates, and feeds a static site.
4. **Site** – an Astro static site with flight, route, airport, and airline pages plus a connection checker.

The full plan, milestones, and acceptance criteria are in `docs/PLAN.md`. Data-source specifics are in `docs/DATA_NOTES.md`.

## Stack

- Python 3.12, managed with `uv`
- DuckDB + Parquet for storage and analytics
- `pytest` for tests, `ruff` for lint and formatting
- Astro for the site, with charts rendered as inline SVG at build time
- Docker System to run the pipelines. Use docker compose for local development. 

Dev dependencies (test, lint, type-check, tooling) can be added as needed. Ask
before adding a **runtime** dependency not listed above — anything that ships in
the pipeline or the built site.

Current dev-only additions: `playwright` and `@astrojs/check` + `typescript` in
`site/`, for screenshots and site type-checking.

## Repository layout

```
pipeline/            Python package: ingest, normalize, validate, metrics, export
  sources/           One module per data source (source adapters)
  models/            Canonical schema definitions
  metrics/           SQL views and metric functions
  gates/             Quality gate rules
  summaries/         Rule-based summary text
  export/            Page JSON + sitemap generation
site/                Astro site
data/                Local data (gitignored): raw/, clean/, export/
tests/               pytest suite, with small fixture files in tests/fixtures/
docs/                PLAN.md, DATA_NOTES.md, DECISIONS.md, PROGRESS.md
  screenshots/       Renderings or Screenshots of the Site
scripts/             Scripts regarding development
docker/              Any docker needs
```

## Common commands

Keep this section current as commands are added.

Python, directly:

```
uv sync                                              # install Python deps
uv run pytest                                        # run tests
uv run ruff check . && uv run ruff format --check .
uv run python -m pipeline status                     # what is on disk
uv run python -m pipeline verify-source --month 2025-01   # REQUIRED before ingest
uv run python -m pipeline ingest --months 2026-01    # download + normalize
uv run python -m pipeline ingest --months 2024-01..2024-12   # a range
uv run python -m pipeline build                      # DuckDB metric views
uv run python -m pipeline export                     # page JSON + quality gates
uv run python -m pipeline query "SELECT ..."         # read-only SQL
```

Site checks:

```
cd site && npm run check                             # astro check (types)
make check-site                                      # the same thing
```

Through Docker (see `docker/README.md`); `make` sets HOST_REPO_PATH for you:

```
make up                          # dashboard :8000, Dagu :8080, DuckDB UI :4213, site :8081
make verify-source MONTH=2025-01
make ingest MONTHS=2024-01..2024-12
make site                        # export pages + build the Astro site
make test / make lint            # in the pipeline image
make ci                          # run .github/workflows locally via act
make help                        # everything else
```

Site, directly:

```
cd site && npm install && npm run dev
PAGES_DIR=../data/export npm run build
```

Design work (synthetic data, never mixed with real data):

```
make mockup          # generate data/mockup/ and build site/dist-mockup/
make mockup-site     # rebuild the mockup site from existing synthetic data
make screenshots     # capture docs/screenshots/ from the mockup build
```

Screenshots need Chromium once: `cd site && npx playwright install chromium`.

## Working agreement

- Work milestone by milestone from `docs/PLAN.md`. Pick the next unchecked task, finish it, and check it off.
- Keep changes small and reviewable. One task per commit where practical, with a clear message.
- Log any meaningful design choice in `docs/DECISIONS.md` (date, decision, reason, alternatives).
- Update `docs/PROGRESS.md` at the end of each session: what changed, what's next, open questions.
- Write tests alongside code. Metric logic must have tests against hand-computed fixtures.
- If something in the plan looks wrong or a source behaves differently than documented, stop and flag it rather than working around it silently.

## Hard rules

- **Never invent data.** No placeholder statistics in pages, fixtures that pretend to be real, or guessed field meanings. If a field's meaning is unclear, check the BTS documentation and record what you found in `docs/DATA_NOTES.md`.
- **Verify before hardcoding.** Download URLs, file formats, and column names must be confirmed against the live source before code depends on them. This is enforced: `pipeline ingest` refuses to run without a verification record from `pipeline verify-source`, and changing the column mapping invalidates an old record.
- **Public data only.** Use only the sources listed in `docs/DATA_NOTES.md`. Do not scrape FlightAware, Flightradar24, Google Flights, airline sites, or any site whose terms prohibit it.
- **Be polite to sources.** Throttle downloads, cache everything, and never re-download a file whose checksum hasn't changed.
- **Raw data is immutable.** Store downloads as received, with a checksum and fetch timestamp. All transformations happen downstream.
- **Quality gates are not optional.** Every generated page must pass through the gate runner, which returns `publish`, `noindex`, or `drop`. A gate whose input does not exist yet must report itself as *skipped* in the report, never pass silently.
- **Summary text is rule-based.** Page summaries come from deterministic, tested rules in `pipeline/summaries/`, not from a language model at build time. Templates phrase nothing: a verdict word like "usually late" is summary text and belongs in a rule.
- **Mockup data is quarantined.** Synthetic data for design work lives in `data/mockup/`, builds to `site/dist-mockup/`, and every page it produces carries a visible banner and is forced to `noindex`. Never point a real build at it.
- **Credit the source.** Every page states that data comes from the U.S. Department of Transportation, Bureau of Transportation Statistics, and shows the data period.
- **No secrets in the repo.** Use environment variables and `.env` (gitignored).

## Domain definitions (use these consistently)

- **On time:** arrived less than 15 minutes after scheduled arrival (BTS `ArrDel15 = 0`), among flights that operated.
- **Operated flight:** not cancelled and not diverted.
- **Cancellation rate:** cancelled flights ÷ scheduled flights.
- **Trailing 12 months:** the 12 most recent months available in the data, not the 12 months before today.
- **Flight identity:** carrier + flight number + origin + destination. See `docs/DATA_NOTES.md` for the open question on reporting vs marketing carrier.

If a definition needs to change, update it here and log it in `docs/DECISIONS.md`.

## Owner context

The owner is an experienced C++ engineer doing this as a personal side project on personal equipment and time. Explain Python/web-specific choices briefly when they aren't obvious, but skip basics.
