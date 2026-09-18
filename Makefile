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
.PHONY: help up down restart logs ps dash build-images pull doctor smoke reset \
        verify-source ingest normalize build export status query sql \
        site site-build dev test lint fmt check-site ci ci-list shell clean clean-data \
        mockup mockup-site themes screenshots check-links

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Dashboard:  http://localhost:$${DASHBOARD_PORT:-8000}"

# --- stack ---------------------------------------------------------------

# Delegates rather than duplicating: the script creates .env, checks that Docker
# is actually running, and waits for each service to answer instead of returning
# the moment compose exits.
up: ## Start the stack and wait until every service answers
	./scripts/stack.sh up

doctor: ## Check this machine can run the stack
	./scripts/doctor.sh

smoke: ## Run everything CI runs, locally (add --fast to skip end-to-end)
	./scripts/smoke.sh

reset: ## Stop the stack, drop volumes, delete derived data
	./scripts/stack.sh reset

down: ## Stop everything (keeps volumes and data)
	./scripts/stack.sh down

restart: ## Restart the long-running services
	$(COMPOSE) restart dashboard dagu duckdb-ui web

logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=80

# Named `ps`, not `status`: `make status` is the pipeline's data status.
ps: ## Show which services are running and answering
	./scripts/stack.sh status

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

# --- mockup --------------------------------------------------------------
#
# A synthetic dataset for design review. It never touches data/ or site/dist:
# generated data lives in data/mockup/ and the build in site/dist-mockup/, and
# every page it produces is stamped as synthetic and forced to noindex.

mockup: ## Generate synthetic data and build the mockup site
	uv run python scripts/make_mockup_data.py
	$(MAKE) mockup-site

mockup-site: ## Rebuild the mockup site from existing synthetic data
	cd site && SITE_THEME=$(THEME) PAGES_DIR=$(CURDIR)/data/mockup/export OUT_DIR=dist-mockup npm run build

# Colour scheme. See the header of site/public/styles/global.css for the list.
THEME ?= ocean

themes: ## Build the mockup in every colour scheme, into site/dist-<theme>/
	@for t in ocean harbor paper; do \
	  echo "building $$t..."; \
	  (cd site && SITE_THEME=$$t PAGES_DIR=$(CURDIR)/data/mockup/export OUT_DIR=dist-$$t npm run build >/dev/null) || exit 1; \
	done
	@echo "Compare: site/dist-ocean, site/dist-harbor, site/dist-paper"

screenshots: ## Screenshot the mockup into docs/screenshots
	node scripts/screenshot_site.mjs

check-links: ## Verify every internal link in the mockup build resolves
	node scripts/check_links.mjs site/dist-mockup

# --- checks --------------------------------------------------------------

test: ## Run pytest in the pipeline image
	$(RUN) --entrypoint sh pipeline -lc "pytest -q"

lint: ## ruff check + format check
	$(RUN) --entrypoint sh pipeline -lc "ruff check . && ruff format --check ."

check-site: ## Type-check the Astro site
	cd site && npm run check

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
