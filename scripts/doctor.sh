#!/usr/bin/env bash
# Check this machine can run the stack, before you find out the hard way.
#
# Exits 0 if everything needed is present, 1 if something is genuinely broken.
# Warnings (optional tools, busy ports) do not fail the run.
#
#   ./scripts/doctor.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

FAIL=0
WARN=0

if [ -t 1 ]; then
  OK=$'\033[32m  ok \033[0m'; BAD=$'\033[31mFAIL \033[0m'; WRN=$'\033[33mwarn \033[0m'; DIM=$'\033[2m'; OFF=$'\033[0m'
else
  OK="  ok "; BAD="FAIL "; WRN="warn "; DIM=""; OFF=""
fi

ok()   { printf '%s %s\n' "$OK" "$1"; }
bad()  { printf '%s %s\n' "$BAD" "$1"; [ $# -gt 1 ] && printf '       %s%s%s\n' "$DIM" "$2" "$OFF"; FAIL=$((FAIL+1)); }
warn() { printf '%s %s\n' "$WRN" "$1"; [ $# -gt 1 ] && printf '       %s%s%s\n' "$DIM" "$2" "$OFF"; WARN=$((WARN+1)); }
section() { printf '\n%s\n' "$1"; }

section "Container runtime"

if command -v docker >/dev/null 2>&1; then
  ok "docker $(docker --version | sed 's/Docker version //;s/,.*//')"
  if docker info >/dev/null 2>&1; then
    ok "docker daemon is reachable"
  else
    bad "docker daemon is not reachable" \
        "Start Docker Desktop, or: sudo systemctl start docker"
  fi
  if docker compose version >/dev/null 2>&1; then
    ok "docker compose $(docker compose version --short 2>/dev/null)"
  else
    bad "docker compose v2 not found" "The v1 'docker-compose' script will not work; this repo needs the plugin."
  fi
else
  bad "docker not installed" "https://docs.docker.com/get-docker/"
fi

section "Toolchain"

if command -v uv >/dev/null 2>&1; then
  ok "uv $(uv --version | awk '{print $2}')"
else
  warn "uv not installed" "Only needed to run the pipeline outside Docker: https://docs.astral.sh/uv/"
fi

if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node --version | sed 's/v//;s/\..*//')"
  if [ "$NODE_MAJOR" -ge 20 ]; then
    ok "node $(node --version)"
  else
    warn "node $(node --version) is older than the v20 Astro expects"
  fi
else
  warn "node not installed" "Only needed to build the site outside Docker."
fi

command -v git >/dev/null 2>&1 && ok "git $(git --version | awk '{print $3}')" || bad "git not installed"

section "Configuration"

if [ -f .env ]; then
  ok ".env exists"
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
  if [ "${HOST_REPO_PATH:-}" = "$REPO" ]; then
    ok "HOST_REPO_PATH matches this directory"
  elif [ -n "${HOST_REPO_PATH:-}" ]; then
    warn "HOST_REPO_PATH is '$HOST_REPO_PATH', not '$REPO'" \
         "make sets it automatically; this only matters for bare 'docker compose' calls."
  else
    warn "HOST_REPO_PATH is not set in .env" "make sets it automatically. Set it if you call docker compose directly."
  fi
else
  warn ".env does not exist" "cp .env.example .env  (make up works without it, using defaults)"
fi

if docker info >/dev/null 2>&1; then
  if HOST_REPO_PATH="$REPO" docker compose -f docker/compose.yml config -q 2>/dev/null; then
    ok "docker/compose.yml is valid"
  else
    bad "docker/compose.yml failed to parse" "HOST_REPO_PATH='$REPO' docker compose -f docker/compose.yml config"
  fi
fi

section "Ports"

check_port() {
  local port="$1" name="$2"
  if command -v nc >/dev/null 2>&1 && nc -z 127.0.0.1 "$port" 2>/dev/null; then
    warn "port $port ($name) is already in use" "Change it in .env, or stop whatever is listening."
  elif command -v ss >/dev/null 2>&1 && ss -lnt 2>/dev/null | grep -q ":$port "; then
    warn "port $port ($name) is already in use" "Change it in .env, or stop whatever is listening."
  else
    ok "port $port ($name) is free"
  fi
}
check_port "${DASHBOARD_PORT:-8000}" dashboard
check_port "${DAGU_PORT:-8080}" dagu
check_port "${WEB_PORT:-8081}" site
check_port "${DUCKDB_UI_PORT:-4213}" "duckdb ui"

section "Disk"

AVAIL_KB="$(df -Pk . | awk 'NR==2 {print $4}')"
AVAIL_GB=$(( AVAIL_KB / 1024 / 1024 ))
if [ "$AVAIL_GB" -ge 10 ]; then
  ok "${AVAIL_GB}G free"
elif [ "$AVAIL_GB" -ge 3 ]; then
  warn "${AVAIL_GB}G free" "Images and a few years of BTS data want ~10G."
else
  bad "${AVAIL_GB}G free" "Not enough room for the images."
fi

section "Project state"

if [ -f data/verification/bts_ontime_reporting_carrier.json ]; then
  ok "BTS source is verified"
else
  warn "BTS source is NOT verified" "Nothing can be ingested until: make verify-source MONTH=2025-01"
fi

MONTHS=$(find data/clean/operations -name 'operations_*.parquet' 2>/dev/null | wc -l | tr -d ' ')
if [ "$MONTHS" -gt 0 ]; then
  ok "$MONTHS month(s) of real data normalized"
else
  warn "no real data ingested yet" "The mockup (make mockup) does not need any."
fi

[ -f data/mockup/export/manifest.json ] && ok "mockup export present" \
  || warn "no mockup export" "make mockup"

printf '\n'
if [ "$FAIL" -gt 0 ]; then
  printf '%s%d problem(s), %d warning(s).%s\n' "$DIM" "$FAIL" "$WARN" "$OFF"
  exit 1
fi
printf '%sReady. %d warning(s).%s\n' "$DIM" "$WARN" "$OFF"
