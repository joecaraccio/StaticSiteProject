# Usually Late

A flight reliability site that helps U.S. travelers decide **which flight to
book**, using public U.S. DOT / BTS on-time performance data. Planning tool
first, not live flight tracking.

Full plan and milestones: [`docs/PLAN.md`](docs/PLAN.md).
Source facts and what is still unverified: [`docs/DATA_NOTES.md`](docs/DATA_NOTES.md).

## Status

The pipeline, metrics, quality gates, page export and a first-pass Astro site are
built and tested. **The BTS source itself is not yet verified**, so no real data
has been ingested — see below.

```
BTS download ──► data/raw/ (immutable, checksummed)
                     │
                     ▼  normalize
              data/clean/*.parquet ──► DuckDB views (metrics)
                     │
                     ▼  export + gates
              data/export/*.json ──► Astro static site
```

## Getting started

Everything runs in Docker:

```
cp .env.example .env     # set HOST_REPO_PATH to this directory
make up                  # dashboard on http://localhost:8000
```

The dashboard links to the CI/CD server, the database viewer and the site. See
[`docker/README.md`](docker/README.md) for what each service does.

Or work directly with Python:

```
uv sync
uv run pytest
uv run python -m pipeline status
```

## First: verify the source

The pipeline **refuses to ingest** until the BTS source has been confirmed
against the live site. This is deliberate — CLAUDE.md requires download URLs and
column names to be verified before code depends on them, and that rule is
enforced in code rather than left to discipline.

```
make verify-source MONTH=2025-01
```

It probes the candidate URLs, downloads one month, reads the real CSV header out
of the zip, diffs it against the expected mapping, and prints a block to paste
into `docs/DATA_NOTES.md`. If a URL has moved it says so and points you at the
BTS database page.

Then:

```
make ingest MONTHS=2024-01..2024-12
make build
make site
```

## Layout

| Path | What |
|---|---|
| `pipeline/` | Ingest, normalize, metrics, gates, export |
| `site/` | Astro static site, reads `data/export/` and never a database |
| `docker/` | The local stack: dashboard, Dagu CI/CD, DuckDB UI, nginx, act |
| `docs/` | Plan, data notes, decisions, progress |
| `tests/` | pytest suite with a synthetic, hand-computed fixture |
| `data/` | Local data, gitignored in full |

## Data source

U.S. Department of Transportation, Bureau of Transportation Statistics, Airline
On-Time Performance. Public federal data. No commercial flight-tracking sources
are used — see the "Sources we do not use" section of `docs/DATA_NOTES.md`.
