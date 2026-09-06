#!/usr/bin/env bash
# Local full run, mirroring the GitHub Action: sync state -> poll (alert Discord
# on new) -> push refreshed state back. Run from anywhere; cd's to its own dir.
#
#   ./run.sh              # sync, poll, push state
#   ./run.sh --no-push    # sync + poll only (let the cloud own state)
#
# Needs: JOBS_DISCORD_WEBHOOK (from .env) for alerts, and working `git push`
# auth (gh/PAT) if pushing. Poll still works without either — just no alert/push.
set -euo pipefail
cd "$(dirname "$0")"

PUSH=1
[[ "${1:-}" == "--no-push" ]] && PUSH=0

# 1. Sync. The Action commits seen.json/listings.csv every run, so ours go stale.
#    Discard any local drift in JUST those two files (cloud state is authoritative),
#    then pull. config.toml and everything else are untouched.
echo "==> syncing state from origin"
git checkout -- seen.json listings.csv 2>/dev/null || true
git pull --ff-only || { echo "!! pull not fast-forward — resolve by hand, then rerun"; exit 1; }

# 2. Poll: fetch feeds+boards, alert Discord on genuinely new roles, rewrite state.
echo "==> polling"
[[ -f .env ]] && source .env
python3 jobs.py poll

# 3. Push refreshed state (skip if nothing changed or --no-push).
if [[ "$PUSH" == 1 ]]; then
  if [[ -n "$(git status --porcelain seen.json listings.csv)" ]]; then
    echo "==> pushing state"
    git add seen.json listings.csv
    git commit -m "poll: refresh state"
    # if the Action pushed while we ran, sync and retry once
    git push || { echo "   push rejected, re-syncing…"; git pull --rebase && git push; }
  else
    echo "==> no state change, nothing to push"
  fi
fi
echo "==> done"
