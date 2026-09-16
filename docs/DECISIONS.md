# Decisions

Record meaningful choices here, newest first.

## Template

### YYYY-MM-DD · Title
- **Decision:**
- **Why:**
- **Alternatives considered:**
- **Revisit if:**

---

### 2026-09-15 · Initial stack
- **Decision:** Python 3.12 + uv, DuckDB + Parquet, pytest + ruff, Astro static site, Docker.
- **Why:** Fast local analytics without a server, simple deploys, low running cost.
- **Alternatives considered:** Postgres (heavier to run), Next.js (more runtime complexity), C++ pipeline (slower iteration for data wrangling).
- **Revisit if:** host file limits force on-demand rendering, or data volume outgrows a single machine.
-   NextJs was strongly considered. I still want to use react so a lot of the decisions would translate
