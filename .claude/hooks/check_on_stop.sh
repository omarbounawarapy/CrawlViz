#!/usr/bin/env bash
# Stop hook for builder agents: the work is not finished until the checks for the
# files it touched pass. Exit 2 sends the failure back to the agent to fix.
set -uo pipefail

input="$(cat)"
# Second stop in a row: report, do not loop. The lead re-runs the full checks anyway.
if printf '%s' "$input" | grep -q '"stop_hook_active": *true'; then
  echo "check_on_stop: checks still failing; say so in your report." >&2
  exit 0
fi

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 0
if ! output="$(make --no-print-directory check-changed 2>&1)"; then
  printf 'make check-changed failed. Fix it before you finish:\n%s\n' \
    "$(printf '%s' "$output" | tail -n 60)" >&2
  exit 2
fi
exit 0
