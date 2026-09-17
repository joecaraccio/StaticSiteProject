# Front door for the Docker stack. Every target is a thin wrapper around
# docker compose, so nothing here hides behaviour you cannot reproduce by hand.
#
# HOST_REPO_PATH is exported for all targets: Dagu and act start sibling
# containers on the host daemon, whose bind mounts need host paths.

COMPOSE := docker compose -f docker/compose.yml
export HOST_REPO_PATH := $(CURDIR)

# Long-running services vs. one-shot tool containers.
RUN := $(COMPOSE) run --rm

.DEFAULT_GOAL := help
.PHONY: help up down restart logs ps dash build-images pull \
        verify-source ingest normalize build export status query sql \
        site site-build dev test lint fmt ci ci-list shell clean clean-data

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Dashboard:  http://localhost:$${DASHBOARD_PORT:-8000}"

# --- stack ---------------------------------------------------------------

up: build-images ## Start dashboard, Dagu, DuckDB UI and the site server
	$(COMPOSE) up -d dashboard dagu duckdb-ui web
	@echo ""
	@echo "  Dashboard   http://localhost:$${DASHBOARD_PORT:-8000}   <- start here"
	@echo "  Dagu        http://localhost:$${DAGU_PORT:-8080}"
	@echo "  DuckDB UI   http://localhost:$${DUCKDB_UI_PORT:-4213}"
	@echo "  Site        http://localhost:$${WEB_PORT:-8081}"

down: ## Stop everything (keeps volumes and data)
	$(COMPOSE) down

restart: ## Restart the long-running services
	$(COMPOSE) restart dashboard dagu duckdb-ui web

logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=80

ps: ## Show service status
	$(COMPOSE) ps

dash: ## Open the dashboard in a browser
	@python3 -m webbrowser "http://localhost:$${DASHBOARD_PORT:-8000}" 2>/dev/null \
	  || echo "Open http://localhost:$${DASHBOARD_PORT:-8000}"

build-images: ## Build the pipeline and viewer images
	$(COMPOSE) build pipeline duckdb-ui

pull: ## Pull the third-party images (dagu, node, nginx)
	$(COMPOSE) pull dagu web dashboard site-build

# --- pipeline ------------------------------------------------------------

# Set on the command line, e.g. MONTH=2025-01 or MONTHS=2024-01..2024-12
MONTH ?=
MONTHS ?=

verify-source: ## Confirm the live BTS source. MONTH=YYYY-MM (needs network)
	@test -n "$(strip $(MONTH))" || { echo "Usage: make verify-source MONTH=2025-01"; exit 2; }
	$(RUN) pipeline verify-source --month $(MONTH)

ingest: ## Download + normalize months. MONTHS="2024-01..2024-12"
	@test -n "$(strip $(MONTHS))" || { echo 'Usage: make ingest MONTHS="2024-01..2024-12"'; exit 2; }
	$(RUN) pipeline ingest --months $(MONTHS)

normalize: ## Re-derive Parquet from raw on disk. MONTHS=...
	@test -n "$(strip $(MONTHS))" || { echo 'Usage: make normalize MONTHS="2024-01"'; exit 2; }
	$(RUN) pipeline normalize --months $(MONTHS)

build: ## Rebuild the DuckDB metric views
	$(RUN) pipeline build --verbose

export: ## Export page JSON and run the quality gates
	$(RUN) pipeline export

status: ## What is on disk, and whether the source is verified
	$(RUN) pipeline status

SQL ?=
query sql: ## Run SQL against the built database. SQL="SELECT ..."
	@test -n "$(strip $(SQL))" || { echo 'Usage: make query SQL="SELECT 1"'; exit 2; }
	$(RUN) pipeline query "$(SQL)"

# --- site ----------------------------------------------------------------

site: export site-build ## Export pages, then build the static site

site-build: ## Build the Astro site from the exported JSON
	$(COMPOSE) run --rm site-build

dev: ## Astro dev server with hot reload
	$(COMPOSE) --profile dev up site-dev

# --- checks --------------------------------------------------------------

test: ## Run pytest in the pipeline image
	$(RUN) --entrypoint sh pipeline -lc "pytest -q"

lint: ## ruff check + format check
	$(RUN) --entrypoint sh pipeline -lc "ruff check . && ruff format --check ."

fmt: ## Apply ruff formatting
	$(RUN) --entrypoint sh pipeline -lc "ruff check --fix . && ruff format ."

ci: ## Run .github/workflows locally with act (full GitHub parity)
	$(COMPOSE) run --rm ci push --job check

ci-list: ## List the jobs act would run
	$(COMPOSE) run --rm ci -l

shell: ## Shell inside the pipeline image
	$(RUN) --entrypoint sh pipeline

# --- cleanup -------------------------------------------------------------

clean: ## Remove build output and caches, keep data/
	rm -rf site/dist site/.astro .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

clean-data: ## Delete derived data. Raw downloads are kept.
	rm -rf data/clean data/export
	@echo "data/raw kept: re-downloading is rude to BTS. Use 'rm -rf data/raw' if you really mean it."
