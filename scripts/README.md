# Scripts

Development tooling. Everything here is also reachable through `make`; the
scripts are where the logic lives, the Makefile is the front door.

| Script | `make` | What it does |
|---|---|---|
| `doctor.sh` | `make doctor` | Checks this machine can run the stack: Docker daemon, compose v2, toolchain, `.env`, port conflicts, disk, and what data exists. Run it first, and again whenever something is odd. |
| `stack.sh` | `make up` / `down` / `status` / `reset` | Starts the stack and **waits until each service actually answers**, rather than returning when compose exits. Creates `.env` if missing and always sets `HOST_REPO_PATH` correctly. |
| `smoke.sh` | `make smoke` | Everything CI runs, locally, in about 20 seconds: ruff, pytest, `astro check`, then the full synthetic chain and a link check. Run before pushing. |
| `make_mockup_data.py` | `make mockup` | Generates seeded synthetic data and pushes it through the real pipeline. Output is quarantined and every page is labelled — see the file header. |
| `screenshot_site.mjs` | `make screenshots` | Captures `docs/screenshots/` from the mockup build, in light, dark and at phone width. |
| `check_links.mjs` | `make check-links` | Verifies every internal link in a build resolves. The gates drop pages, so links built from URL patterns can point at nothing. |

## Notes

**`stack.sh up` is the one to use for a first run.** `docker compose up -d`
returns as soon as the containers start, which is well before Dagu has loaded its
DAGs or the DuckDB UI has fetched its extension. The script polls each port and
tells you which service did not come up, with the command to see its logs.

**`smoke.sh` also checks the committed mockup.** `data/mockup/export/` is in git
and its export timestamp is pinned, so re-running the generator should produce no
diff. If it does, the pipeline's output changed — which is either the point of
your change, or a surprise worth looking at.

**The scripts assume they can find the repo from their own location**, so they
work from any directory.
