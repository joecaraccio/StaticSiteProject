# The local stack

Everything runs on one machine through `docker compose`. `make up` starts the
long-running services; the dashboard links to the rest.

```
make up          # dashboard, Dagu, DuckDB UI, site server
make dash        # open the dashboard
make down        # stop (data and volumes are kept)
```

| Service | Port | What it is |
|---|---|---|
| **dashboard** | 8000 | One page linking to everything, with live health checks and the pipeline's current state. **Start here.** |
| **dagu** | 8080 | The CI/CD server: schedules, run history, logs |
| **duckdb-ui** | 4213 | DuckDB's own web UI — SQL editor and schema browser |
| **web** | 8081 | The built static site, served the way a static host would |
| **site-dev** | 4321 | Astro dev server, `make dev` (profile `dev`) |
| **pipeline** | — | One-shot container behind the `make` targets (profile `tools`) |
| **ci** | — | `act`, running the real GitHub workflow locally (profile `tools`) |

Ports are overridable in `.env` — copy `.env.example` to start.

## The CI/CD part

Two complementary things, because they answer different questions.

**`make ci` runs `.github/workflows/ci.yml` through act**, in the same runner
images GitHub uses. This is the "will CI pass?" answer, and because it executes
the actual workflow file, local and GitHub CI cannot drift.

**Dagu owns the schedule.** It is a single container with a web UI, cron, run
history and logs, and its steps start sibling containers on the host Docker
daemon via `action: docker.run`. The DAGs live in `docker/dagu/dags/` and are the
whole definition — there is no build script hiding elsewhere.

| DAG | Schedule | What it does |
|---|---|---|
| `refresh` | 04:00 on the 8th | Ingest the newest BTS month → metrics → page JSON → site build |
| `site-only` | manual | Re-export and rebuild the site without touching BTS |
| `checks` | Mondays 07:00 | ruff + pytest, for a fast signal between pushes |

`refresh` defaults to the month two months back, because BTS publishes a month a
few weeks after it closes. It skips overlapping runs and catches up a missed one
within 48 hours.

Because the `web` service serves `site/dist` directly, a finished build is live
as soon as the files land. There is nothing to deploy locally.

## The data viewer

`duckdb-ui` runs DuckDB's built-in web UI. It opens **its own** database file
(`data/clean/viewer.duckdb`) whose views point at the same Parquet, so a browser
tab left open never takes the write lock that would make `pipeline build` fail.

The `ui` extension is downloaded on first start and cached in a Docker volume, so
only the first run needs to reach `extensions.duckdb.org`. If the service logs a
failure to load the extension, that is why.

Restart it after an ingest to pick up newly added months:

```
docker compose -f docker/compose.yml restart duckdb-ui
```

## Things worth knowing before the first run

**`HOST_REPO_PATH` must be this repo's path on the host.** Dagu and act ask the
host Docker daemon to start sibling containers, and the host resolves their bind
mounts — a path that only exists inside a container would silently mount an empty
directory. `make` sets it for you; set it in `.env` if you run `docker compose`
directly. Compose fails with a clear message if it is missing.

**The Docker socket is mounted into Dagu and into the act container.** That grants
those containers control of the host daemon. It is what makes a local CI server
possible, and it is why this stack binds to localhost and should not be exposed to
a network.

**Dagu runs as root** so it can talk to the socket. If your daemon socket is
group-readable, drop `user: root` and use `group_add` instead.

**The stack has not been run end to end yet.** It was written in an environment
with no Docker daemon, so the compose file is validated (`docker compose config`
passes for every profile) and the DAG syntax was checked against Dagu's own
documentation, but the first `make up` is genuinely a first run. Expect to fix
something small; the likely candidates are socket permissions on the Dagu
container and the DuckDB UI's extension download.

## First run

```
cp .env.example .env          # set HOST_REPO_PATH
make up
make verify-source MONTH=2025-01   # REQUIRED before any ingest; needs network
make ingest MONTHS=2024-01..2024-12
make site
```

`make status` at any point says what is on disk and whether the source is
verified.
