#!/usr/bin/env bash
# Run everything CI runs, locally, before you push.
#
# Mirrors .github/workflows/ci.yml: lint, format, tests, site type-check, then
# the end-to-end chain on synthetic data with a link check. Takes about a minute.
#
#   ./scripts/smoke.sh            everything
#   ./scripts/smoke.sh --fast     skip the end-to-end chain (lint + tests only)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

FAST=0
[ "${1:-}" = "--fast" ] && FAST=1

if [ -t 1 ]; then B=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'; OFF=$'\033[0m'
else B=""; DIM=""; RED=""; GRN=""; OFF=""; fi

FAILED=()
STARTED=$(date +%s)

# Run a step, capturing output and only showing it when the step fails: a green
# run should be quiet enough to read at a glance.
step() {
  local name="$1"; shift
  printf '%s>>%s %s ' "$DIM" "$OFF" "$name"
  local out start elapsed
  start=$(date +%s)
  if out="$("$@" 2>&1)"; then
    elapsed=$(( $(date +%s) - start ))
    printf '%sok%s %s(%ss)%s\n' "$GRN" "$OFF" "$DIM" "$elapsed" "$OFF"
  else
    elapsed=$(( $(date +%s) - start ))
    printf '%sFAILED%s %s(%ss)%s\n' "$RED" "$OFF" "$DIM" "$elapsed" "$OFF"
    printf '%s\n' "$out" | sed 's/^/     /'
    FAILED+=("$name")
  fi
}

site_build() { ( cd site && PAGES_DIR="$REPO/data/mockup/export" OUT_DIR=dist-mockup npm run build ); }
site_check() { ( cd site && npm run check ); }
site_deps()  { ( cd site && npm ci --no-audit --no-fund ); }

printf '%sChecks%s\n' "$B" "$OFF"
step "ruff lint          " uv run ruff check .
step "ruff format        " uv run ruff format --check .
step "pytest             " uv run pytest -q

if [ ! -d site/node_modules ]; then
  printf '%sInstalling site dependencies...%s\n' "$DIM" "$OFF"
  step "npm ci             " site_deps
fi
step "astro check        " site_check

if [ "$FAST" -eq 0 ]; then
  printf '\n%sEnd to end (synthetic data)%s\n' "$B" "$OFF"
  step "generate + export  " uv run python scripts/make_mockup_data.py
  step "site build         " site_build
  step "internal links     " node scripts/check_links.mjs site/dist-mockup

  # The committed mockup export is pinned, so a re-run must not change it.
  # A diff here means the pipeline's output changed — intended or not.
  if git diff --quiet -- data/mockup/export 2>/dev/null; then
    printf '%s>>%s committed mockup   %sunchanged%s\n' "$DIM" "$OFF" "$GRN" "$OFF"
  else
    printf '%s>>%s committed mockup   %schanged%s %s(git diff data/mockup/export)%s\n' \
      "$DIM" "$OFF" "$RED" "$OFF" "$DIM" "$OFF"
    printf '     %sPipeline output differs from what is committed. Review, then commit it.%s\n' "$DIM" "$OFF"
    FAILED+=("committed mockup changed")
  fi
fi

TOTAL=$(( $(date +%s) - STARTED ))
printf '\n'
if [ ${#FAILED[@]} -eq 0 ]; then
  printf '%sAll checks passed in %ss.%s\n' "$GRN" "$TOTAL" "$OFF"
  exit 0
fi
printf '%s%d check(s) failed in %ss:%s\n' "$RED" "${#FAILED[@]}" "$TOTAL" "$OFF"
for f in "${FAILED[@]}"; do printf '  - %s\n' "$f"; done
exit 1
