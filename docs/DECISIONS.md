# Decisions

Record meaningful choices here, newest first.

## Template

### YYYY-MM-DD · Title
- **Decision:**
- **Why:**
- **Alternatives considered:**
- **Revisit if:**

---

### 2026-09-17 · Verification is enforced in code, not by discipline
- **Decision:** `pipeline ingest` refuses to run unless a verification record exists at `data/verification/<source>.json`, matches the current schema fingerprint, and reports no missing required columns. `verify-source` writes that record by downloading a month and reading the real CSV header.
- **Why:** "Verify before hardcoding" is a rule that quietly decays. Making it a precondition means an unverified guess cannot become a dependency, and editing the column mapping automatically invalidates the old record.
- **Alternatives considered:** A checklist in DATA_NOTES.md (what we had — easy to skip); a network test in CI (needs BTS reachable from CI, and would only catch it late).
- **Revisit if:** the verification step becomes an obstacle to legitimate offline work; an `--allow-unverified` escape hatch would then need an equally loud warning.

### 2026-09-17 · Runtime dependencies stay at DuckDB alone
- **Decision:** No pandas, pyarrow, httpx, typer or PyYAML. DuckDB reads CSV and writes Parquet natively; downloads use `urllib`; the CLI uses `argparse`.
- **Why:** CLAUDE.md asks before adding dependencies. Each of these would have earned its place only by saving a few lines, and a small dependency set keeps the container image and the security surface small.
- **Alternatives considered:** pandas for normalization (DuckDB is faster here and already required); httpx for downloads (urllib handles conditional GETs fine).
- **Revisit if:** the summary rule engine (M6) wants YAML, which would justify PyYAML; or retry/backoff needs outgrow urllib.

### 2026-09-17 · Times are stored as reported; hhmm is interpreted in the metrics layer
- **Decision:** `sched_dep`/`actual_dep`/`sched_arr`/`actual_arr` are stored as trimmed strings exactly as BTS reports them. Departure hour is derived in the metrics view as `(hhmm // 100) % 24`, mapping `2400` to hour 0.
- **Why:** The meaning of the time fields is still an open item on the DATA_NOTES checklist. Storing an interpretation would bake an unverified assumption into the Parquet, where it is expensive to undo; deriving it in a view costs nothing to change.
- **Alternatives considered:** Parsing to TIME at normalization (loses `2400` and hides the assumption); storing both (redundant).
- **Revisit if:** verification shows the field is not local hhmm, or that `2400` means something other than midnight ending the day.

### 2026-09-17 · Airport metrics carry an arrival/departure role
- **Decision:** `airport_metrics` is keyed on (airport, role), with each flight appearing once as a departure from its origin and once as an arrival at its destination. Only the departure row drives the airport page URL.
- **Why:** "How reliable is BOS" means different things for departures and arrivals, and a single blended number would hide that.
- **Alternatives considered:** Departures only (loses half the story); two separate page types (more URLs than the content justifies).
- **Revisit if:** the airport template ends up showing only one role, in which case the other is dead weight.

### 2026-09-17 · Rates are NULL on an empty denominator, never 0
- **Decision:** Every rate metric divides by `nullif(denominator, 0)`, and the page templates render NULL as an em dash.
- **Why:** A flight with no measurable operations showing "0% on time" is worse than showing nothing: it is a confident wrong answer, and it would feed the summary rules and the gates.
- **Alternatives considered:** Coalescing to 0 (actively misleading); omitting the field (changes the JSON shape per page).
- **Revisit if:** never, ideally.

### 2026-09-17 · Uncomputed gates are recorded as skipped, not silently passed
- **Decision:** The summary and similarity gates take `None` to mean "not computed yet" (both land in M6). The gate runner records these in a `skipped` list that appears in the CSV report and in each page's JSON, rather than treating them as passes.
- **Why:** "Quality gates are not optional" is a hard rule. An unenforced gate is acceptable while its input does not exist; an *invisible* unenforced gate is how a rule quietly stops applying.
- **Alternatives considered:** Defaulting `summary_rules_matched` to 0 (drops every page until M6); defaulting to 1 (a lie).
- **Revisit if:** M6 lands, at which point both become ordinary gates.

### 2026-09-17 · Local CI/CD is act plus Dagu, not a self-hosted forge
- **Decision:** `act` runs `.github/workflows/ci.yml` locally so local and GitHub CI cannot drift. Dagu (one container, web UI, cron) owns scheduling, run history and logs for the data refresh, driving containers through `action: docker.run`.
- **Why:** The requirement was a CI/CD server that can regenerate the site, not a git host. Gitea + act_runner would add a forge, a runner and docker-in-docker for no benefit on a single machine. Woodpecker needs a forge to authenticate against and adds a second pipeline syntax to maintain.
- **Alternatives considered:** Gitea Actions; Woodpecker; plain cron + Makefile (no UI, no run history).
- **Revisit if:** the project grows a second contributor, where a real forge starts to pay for itself.

### 2026-09-17 · The DuckDB viewer opens its own database file
- **Decision:** The `duckdb-ui` service opens `data/clean/viewer.duckdb`, rebuilding the same views over the same Parquet, rather than opening `usually_late.duckdb`.
- **Why:** DuckDB is single-writer. A browser tab left open would otherwise hold a lock and make `pipeline build` fail, which is a miserable way to learn about file locking.
- **Alternatives considered:** Opening the main database read-only (blocks temp tables, so no scratch work); stopping the viewer around builds (fragile).
- **Revisit if:** DuckDB gains concurrent write access across processes.

### 2026-09-17 · Two charts rather than a second y-axis
- **Decision:** On-time rate and cancellation rate get their own charts on a page, each with its own scale, rather than sharing one plot with two axes.
- **Why:** Cancellation rates sit near 1-2% and on-time rates near 80%. On a shared axis the cancellation line is a flat smear at the baseline; on a second y-axis the crossings are an artifact of the scales, not the data.
- **Alternatives considered:** Dual axis (misleading); indexing both to a common base (obscures the actual percentages, which are the point).
- **Revisit if:** never for these two series.

### 2026-09-17 · Delay severity uses an ordinal ramp, not categorical colours
- **Decision:** The delay-distribution bar colours its buckets with a single-hue ramp, light to dark, with "on time" as a status green and "cancelled or diverted" as a neutral. Palettes were checked with the dataviz validator in both light and dark mode.
- **Why:** The buckets are ordered severity, not distinct identities. Categorical hues would imply the categories are unrelated and make "worse" impossible to read at a glance.
- **Alternatives considered:** Seven categorical hues (exceeds the safe ceiling and reads as unordered); a red-to-green ramp (fails colour-vision checks).
- **Revisit if:** the bucket definitions in PLAN.md §6 stop being ordered.

---

### 2026-09-15 · Initial stack
- **Decision:** Python 3.12 + uv, DuckDB + Parquet, pytest + ruff, Astro static site, Docker.
- **Why:** Fast local analytics without a server, simple deploys, low running cost.
- **Alternatives considered:** Postgres (heavier to run), Next.js (more runtime complexity), C++ pipeline (slower iteration for data wrangling).
- **Revisit if:** host file limits force on-demand rendering, or data volume outgrows a single machine.
-   NextJs was strongly considered. I still want to use react so a lot of the decisions would translate
