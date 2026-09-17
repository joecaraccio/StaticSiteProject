#!/usr/bin/env bash
# Start, stop and inspect the local stack.
#
# `make up` is the thin version of this; the script adds the parts that make a
# first run survivable: it creates .env, checks prerequisites, waits for each
# service to actually answer, and tells you which one did not.
#
#   ./scripts/stack.sh up        start everything and wait until it responds
#   ./scripts/stack.sh down      stop (data and volumes are kept)
#   ./scripts/stack.sh restart
#   ./scripts/stack.sh status    what is running, and what is answering
#   ./scripts/stack.sh logs [service]
#   ./scripts/stack.sh reset     stop, drop volumes, delete derived data
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

export HOST_REPO_PATH="$REPO"
COMPOSE=(docker compose -f docker/compose.yml)
SERVICES=(dashboard dagu duckdb-ui web)

if [ -t 1 ]; then B=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'; OFF=$'\033[0m'
else B=""; DIM=""; RED=""; GRN=""; OFF=""; fi

die() { printf '%s%s%s\n' "$RED" "$1" "$OFF" >&2; exit 1; }

load_env() {
  if [ ! -f .env ]; then
    printf '%sNo .env — creating one from .env.example.%s\n' "$DIM" "$OFF"
    sed "s|^HOST_REPO_PATH=.*|HOST_REPO_PATH=$REPO|" .env.example > .env
  fi
  set -a; . ./.env; set +a
  export HOST_REPO_PATH="$REPO"   # always authoritative, whatever .env says
}

require_docker() {
  command -v docker >/dev/null 2>&1 || die "docker is not installed. Run ./scripts/doctor.sh"
  docker info >/dev/null 2>&1 || die "The docker daemon is not reachable. Run ./scripts/doctor.sh"
}

urls() {
  printf '\n  %sDashboard%s   http://localhost:%s   %s<- start here%s\n' \
    "$B" "$OFF" "${DASHBOARD_PORT:-8000}" "$DIM" "$OFF"
  printf '  Dagu        http://localhost:%s\n' "${DAGU_PORT:-8080}"
  printf '  DuckDB UI   http://localhost:%s\n' "${DUCKDB_UI_PORT:-4213}"
  printf '  Site        http://localhost:%s\n\n' "${WEB_PORT:-8081}"
}

# Poll a port until something answers. Any HTTP response counts: we are checking
# that the service is listening, not that a particular page exists.
wait_for() {
  local name="$1" port="$2" tries="${3:-60}" i=0
  while [ "$i" -lt "$tries" ]; do
    if curl -sS -o /dev/null --max-time 2 "http://127.0.0.1:${port}/" 2>/dev/null; then
      printf '  %s%s%s %-11s :%s\n' "$GRN" "ready" "$OFF" "$name" "$port"
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  printf '  %sslow %s%-11s :%s  %s(docker compose -f docker/compose.yml logs %s)%s\n' \
    "$RED" "$OFF" "$name" "$port" "$DIM" "$name" "$OFF"
  return 1
}

cmd_up() {
  require_docker
  load_env

  printf '%sBuilding images (first run pulls a few hundred MB)...%s\n' "$DIM" "$OFF"
  "${COMPOSE[@]}" build pipeline duckdb-ui

  printf '%sStarting services...%s\n' "$DIM" "$OFF"
  "${COMPOSE[@]}" up -d "${SERVICES[@]}"

  printf '\nWaiting for services to answer:\n'
  local slow=0
  wait_for dashboard "${DASHBOARD_PORT:-8000}" 30 || slow=1
  wait_for dagu      "${DAGU_PORT:-8080}"      60 || slow=1
  # The DuckDB UI downloads its extension on first start, so it gets longer.
  wait_for duckdb-ui "${DUCKDB_UI_PORT:-4213}" 120 || slow=1
  wait_for site      "${WEB_PORT:-8081}"       30 || slow=1

  urls
  if [ "$slow" -ne 0 ]; then
    printf '%sSomething did not come up. Check its logs with the command shown above.%s\n' "$DIM" "$OFF"
    printf '%sThe DuckDB UI needs network access on its first start, to fetch its extension.%s\n\n' "$DIM" "$OFF"
  fi
  if [ ! -f data/mockup/export/manifest.json ] && [ ! -d data/export ]; then
    printf '%sThe site has no pages yet. `make mockup` builds it from synthetic data,%s\n' "$DIM" "$OFF"
    printf '%sor `make verify-source MONTH=2025-01` to start on the real thing.%s\n\n' "$DIM" "$OFF"
  fi
}

cmd_down() { require_docker; load_env; "${COMPOSE[@]}" down; }

cmd_restart() { require_docker; load_env; "${COMPOSE[@]}" restart "${SERVICES[@]}"; }

cmd_status() {
  require_docker; load_env
  "${COMPOSE[@]}" ps
  printf '\nEndpoints:\n'
  wait_for dashboard "${DASHBOARD_PORT:-8000}" 1 || true
  wait_for dagu      "${DAGU_PORT:-8080}"      1 || true
  wait_for duckdb-ui "${DUCKDB_UI_PORT:-4213}" 1 || true
  wait_for site      "${WEB_PORT:-8081}"       1 || true
  printf '\n'
}

cmd_logs() {
  require_docker; load_env
  if [ $# -gt 0 ]; then "${COMPOSE[@]}" logs -f --tail=100 "$1"
  else "${COMPOSE[@]}" logs -f --tail=80; fi
}

cmd_reset() {
  require_docker; load_env
  printf 'This stops the stack, drops its volumes, and deletes derived data.\n'
  printf '%sdata/raw is kept: re-downloading is rude to BTS.%s\n' "$DIM" "$OFF"
  printf 'Continue? [y/N] '
  read -r reply
  case "$reply" in
    [yY]*) ;;
    *) printf 'Cancelled.\n'; return 0 ;;
  esac
  "${COMPOSE[@]}" down -v
  rm -rf data/clean data/export site/dist site/dist-mockup
  printf 'Done. `make mockup` or an ingest will rebuild.\n'
}

case "${1:-up}" in
  up)      shift || true; cmd_up "$@" ;;
  down)    shift || true; cmd_down "$@" ;;
  restart) shift || true; cmd_restart "$@" ;;
  status)  shift || true; cmd_status "$@" ;;
  logs)    shift || true; cmd_logs "$@" ;;
  reset)   shift || true; cmd_reset "$@" ;;
  -h|--help|help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0" ;;
  *) die "Unknown command '$1'. Try: up, down, restart, status, logs, reset" ;;
esac
