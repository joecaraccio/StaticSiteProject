# Decisions

Record meaningful choices here, newest first.

## Template

### YYYY-MM-DD · Title
- **Decision:**
- **Why:**
- **Alternatives considered:**
- **Revisit if:**

---

### 2026-09-19 · The mark is a dial with a plane climbing out of it
- **Decision:** `site/src/components/Logo.astro` holds the single definition of the mark: an open clock dial with a gap, and a plane climbing out through it. `public/favicon.svg` is the same shape with a heavier arc.
- **Why:** It carries both halves of the name in one shape, and it was the only one of five candidates still legible at 22px. The ones that layered a plane over clock hands turned into a smudge; a plane outside the dial read as a stray antenna; dial ticks plus a plane read as a crosshair. Rendering the candidates at real size and looking at them decided it, which is faster and more honest than arguing about it at 200%.
- **Alternatives considered:** plane as the minute hand; plane leaving the rim; plane in a full dial with tick marks; plane plus a single clock hand. All rendered, all rejected on legibility.
- **Revisit if:** the brand name changes, or the mark needs to work in one colour at favicon size on a busy background.

### 2026-09-19 · SVG favicons need stroke and fill on separate classes
- **Decision:** `favicon.svg` declares `.arc { fill: none; stroke: … }` and `.plane { fill: …; stroke: none }` rather than one class setting both.
- **Why:** A favicon cannot inherit `currentColor`, so its colours are declared in an internal stylesheet — and a CSS `fill` beats the `fill="none"` presentation attribute on the element. One combined class filled the arc as well as stroking it and the mark rendered as a solid disc at every size. Caught by rendering it at 16/24/32/48px; it would not have been visible in the source.
- **Alternatives considered:** Presentation attributes only (no dark-mode variant); a PNG favicon (no dark-mode variant either, and more files).
- **Revisit if:** more colour-scheme-aware SVG assets are added — the same trap applies to each.

---

### 2026-09-19 · The layout follows the online-travel-agency idiom
- **Decision:** Reworked the chrome and page structure to the pattern travel booking sites use: a navy sticky header, a coloured hero band with the search lifted onto a card over its lower edge, white cards on a soft canvas, dense result rows with the figure right-aligned and a chevron, and detail pages as a stack of panels. The new `voyager` scheme is the default.
- **Why:** The owner asked for the feel of a booking site. That feel is mostly structural rather than chromatic — elevation, density, and search-first hierarchy — so changing tokens alone would not have got there.
- **What was deliberately not copied:** no other company's name, logo, wordmark or brand colours. The palette is our own and validated independently; the layout conventions are the shared vocabulary of the category, which is fair to use. Building something that could pass for another company's site would not be.
- **Alternatives considered:** Recolouring only (does not change the feel); a photographic hero (needs licensed imagery, and a flight-path motif carries the same weight without it).
- **Revisit if:** the site gains a booking or affiliate flow, where the resemblance could start to imply an affiliation that does not exist.

---

### 2026-09-18 · Themes may change surfaces and hue; status colours are fixed
- **Decision:** `SITE_THEME` selects a colour scheme at build time (`ocean`, `harbor`, `paper`). A theme owns surfaces, text, borders, the primary hue, the delay-severity ramp and the hero gradient. It does **not** own the status roles: on-time green, cancelled neutral, and the four reliability band colours are declared once, outside every theme block.
- **Why:** A red chip has to mean the same thing whatever the site looks like. Letting a theme re-colour the bands would make the meaning of a colour depend on a build flag, and the bands are already tied to thresholds in `pipeline/summaries/rules.py`. This also matches the dataviz guidance that a status palette is fixed and never themed.
- **Alternatives considered:** Theming everything (meaning becomes cosmetic); a single hardcoded scheme (no way to try alternatives without a rewrite).
- **Revisit if:** a theme's surfaces move far enough that a fixed band colour fails contrast against them — the check is cheap and should be re-run per theme.

### 2026-09-18 · Each theme's chart ramp is validated, not hand-picked
- **Decision:** Every theme ships a five-step single-hue ordinal ramp for delay severity, checked with the dataviz validator for monotone lightness, adjacent-step gaps of at least 0.06, and a light end clearing the surface — in both light and dark. Text, link and series colours are checked for contrast against that theme's surface.
- **Why:** Changing the accent hue silently breaks the chart ramp otherwise. The first teal ramp failed on its light end at 1.72:1 against a 2:1 floor and had to be re-stepped; a scheme that looked fine would have shipped an unreadable lightest bucket.
- **Alternatives considered:** Reusing the blue ramp across themes (the chart stops belonging to the page); deriving a ramp programmatically (needs a colour library and still needs checking).
- **Revisit if:** a fourth theme is added — run the validator before writing the CSS, not after.

---

### 2026-09-18 · Reliability bands live in the rule engine, not in CSS
- **Decision:** `pipeline/summaries/rules.py` owns a `BANDS` table (good / warning / serious / critical) used both to phrase the headline sentence and to set `summary.band` in the page JSON. The site maps a band name to a colour and never decides where a band starts.
- **Why:** A colour-coded verdict is a verdict. CLAUDE.md puts verdict language in `pipeline/summaries/`, and the engine already had these exact thresholds hardcoded inside the headline rule. Had the site picked its own, a page could have said "usually on time" beside an amber chip. A test asserts the band and the sentence never disagree.
- **Alternatives considered:** Thresholds in CSS or in the template (two sources of truth); a continuous colour scale (no phrasing to match, and it implies a precision the sample sizes do not support).
- **Revisit if:** the bands need to differ by page type, e.g. a good airport rate is not a good flight rate.

### 2026-09-18 · Rank is carried by a meter, not by hue
- **Decision:** The reliability chip shows a four-segment meter (filled segments = band rank), the percentage, and a band colour. Colour is the third channel, not the first.
- **Why:** Four ordered severity colours cannot be separated far enough by hue once they are dark enough to use as text. Measured with the palette validator, the original set had an adjacent pair at ΔE 0.8 — indistinguishable with full colour vision — and the best re-stepped set, including one with a neutral mid-tone, still only reached 13.7 against a floor of 15. Darkening warm hues converges them on brown; that is a property of the colour space, not a tuning problem.
- **Why not just add labels:** The validator is explicit that a normal-vision ΔE below 15 is a hard fail that secondary encoding does not excuse — *when colour carries identity*. The meter moves identity off colour entirely: segment count is countable and exact, the number is always present, and the chip carries a `title`. Colour then reinforces rather than informs, which is the case the rule is protecting.
- **Alternatives considered:** Three bands instead of four (hides a real distinction the engine makes); a single-hue sequential ramp (loses the good/bad reading that makes the chip worth having); colour plus label only (does not clear the hard floor).
- **Revisit if:** the band count changes, or the chip is ever used somewhere the number cannot be shown.

---

### 2026-09-17 · The synthetic export is committed; the derived binaries are not
- **Decision:** `data/mockup/export/` (103 JSON files, ~1.2 MB) is in git. `data/mockup/clean/` (Parquet, DuckDB) and `data/mockup/raw/` (the zip) are not.
- **Why:** The export is diffable text, so a template or schema change shows up in a PR as a content diff — it doubles as a snapshot test of the whole chain. It also means someone with only Node can build the full site without installing Python or running the pipeline. The Parquet and DuckDB files are binary, rewritten wholesale on every regeneration, and rebuilt in seconds; the raw zip embeds timestamps so it churns even when its contents do not.
- **Alternatives considered:** Committing all of `data/mockup/` (binary churn for no benefit); committing none of it (a frontend contributor must install Python and DuckDB to see a page).
- **Revisit if:** the export grows past a few MB, at which point a trimmed subset would serve the same purpose.

### 2026-09-17 · Exports must be byte-identical for identical input
- **Decision:** Every metrics view read during export carries an explicit `ORDER BY` on its key columns, the manifest's page list is sorted by URL, and `generated_at` can be pinned with `export --generated-at`.
- **Why:** DuckDB's `GROUP BY` gives no ordering guarantee, so two exports of the same data emitted pages in different orders. That made the committed mockup churn, and it would have made any future diff of a real export useless for spotting real changes. `scripts/smoke.sh` now fails if a regeneration alters the committed export.
- **Alternatives considered:** Sorting only the manifest (leaves page-generation order unstable, which any order-sensitive logic added later would inherit); not committing the export (gives up the snapshot-test property).
- **Revisit if:** export becomes slow enough that the sorts matter, which seems unlikely at this scale.

---

### 2026-09-17 · Templates check that a link's target exists
- **Decision:** Any internal link built from a URL pattern rather than from a manifest entry goes through `pageExists()` first. Related links to dropped pages are omitted; an alternative flight with no page of its own still appears in the comparison table, as plain text rather than a link.
- **Why:** The gates drop pages, so "the return route" or "the other flights on this route" may not exist. A link checker over a build with real gate decisions found two broken links immediately, and with real data most routes fall below the 60-operation threshold — this would have produced 404s at scale rather than occasionally.
- **Alternatives considered:** Emitting the related links from the export (the site stays dumber, but export would need a second pass to know the full surviving set); linking anyway and adding a nice 404 page (still a broken link).
- **Revisit if:** export grows a two-pass structure for another reason, at which point moving this server-side is cheap.

### 2026-09-17 · A CI job runs the whole chain on synthetic data
- **Decision:** `.github/workflows/ci.yml` has a job that generates six months of synthetic data, runs ingest → metrics → gates → export, builds the site and checks every internal link.
- **Why:** The unit tests cover each stage; nothing covered the seams between them. This job needs no network access to BTS and catches the class of bug the link checker just found.
- **Alternatives considered:** Checking links only locally (it would not have been run); a real ingest in CI (depends on BTS being reachable and is rude to the source).
- **Revisit if:** the job gets slow enough to be annoying; six months is about 12,000 rows.

---

### 2026-09-17 · Mockup data is quarantined, not forbidden
- **Decision:** Design work uses a seeded generator (`scripts/make_mockup_data.py`) that writes to `data/mockup/`, builds to `site/dist-mockup/`, and passes `--demo-notice` to `export`. Every page it produces carries a visible banner and is forced to `noindex` by the layout, whatever the gates decided. The generator refuses to run against the real data root.
- **Why:** "Never invent data" is about what reaches a published page. A mockup needs numbers to have a shape worth judging, so the resolution is containment rather than abstinence: synthetic figures are allowed as long as they are unmistakable, unindexable, and cannot end up in a real build.
- **Alternatives considered:** No mockup at all (leaves the templates unreviewable until real data exists, which is the wrong order); hand-drawn static mockups (they drift from the real templates immediately); fake data in the real export directory (exactly what the rule forbids).
- **Revisit if:** real data lands, at which point the mockup is only needed for edge cases the real data does not contain.

### 2026-09-17 · The mockup runs through the real pipeline
- **Decision:** The generator emits rows in the BTS *source* column layout and pushes them through the actual normalize → build → export path, rather than writing page JSON directly.
- **Why:** A mockup that bypasses the pipeline only tells you about the templates. This one exercises the schema, the metrics, the gates and the summary rules, so the screenshots are evidence the system works end to end — and it caught real bugs.
- **Alternatives considered:** Fabricating page JSON (faster, proves nothing).
- **Revisit if:** generation time becomes a problem; 24 months is about 48,000 rows and a few seconds.

### 2026-09-17 · Summary rules are Python functions, not YAML (for now)
- **Decision:** `pipeline/summaries/rules.py` declares each rule as a function over a `SummaryContext`, collected in an ordered tuple. PLAN.md M6 specifies YAML rules; this is a deliberate deviation.
- **Why:** The rules need real conditional logic (band thresholds, "one in N" phrasing, suppressing a comparison when the gap is noise). Expressing that in YAML means inventing an expression language and an interpreter for it, which is more code and less testable than the functions themselves. The rules stay deterministic and unit-tested either way, which is what the hard rule actually requires.
- **Alternatives considered:** YAML with a small expression evaluator (more machinery, harder to test); a template string per rule with no conditions (cannot express the bands).
- **Revisit if:** a non-programmer needs to edit the copy, which is the case YAML would earn its keep for.

### 2026-09-17 · A caveat is not a summary
- **Decision:** The `small_sample` rule returns nothing when there is no rate to qualify, so a page with no measurable flights matches zero rules and the gate drops it.
- **Why:** Without this, the only sentence on an empty page was a warning about its own emptiness, and the summary gate counted that as a match — letting a page through on the strength of its disclaimer.
- **Alternatives considered:** Excluding caveat rules from the gate count (more machinery for the same result).
- **Revisit if:** more caveat-shaped rules appear, which would make a rule "kind" worth modelling explicitly.

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
