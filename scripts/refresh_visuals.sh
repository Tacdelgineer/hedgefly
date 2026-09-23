#!/usr/bin/env bash
# Refresh every visual from whatever the runs have produced, then commit and push them.
#
#   bash scripts/refresh_visuals.sh            # by hand
#   (queue/day7.jobs runs it last, as job visuals_refresh)
#
# Uses the newest finished run for the HQ (the validation run once it exists, day6_full until
# then) and day6_full's finale if it has landed. Everything is exported from the logs, so every
# number on screen still comes from runs/ (PLAN.md rule 8). CPU only.
#
# Environment (both optional):
#   HEDGEFLY_MAIN   the checkout that holds .venv, data/ and runs/ (default: this checkout)
#   HEDGEFLY_HOST   the host name printed in the scp hint for the one-file HQ (default: hostname)
set -euo pipefail

W="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAIN="${HEDGEFLY_MAIN:-$W}"
PY="$MAIN/.venv/bin/python"
cd "$W"
[[ -e data && -e runs ]] || { ln -sfn "$MAIN/data" data; ln -sfn "$MAIN/runs" runs; }

RUN=runs/day7_validation
[[ -f "$RUN/run_summary.json" ]] || RUN=runs/day6_full
FINALE=runs/day6_full
echo "refreshing visuals from $RUN (finale from $FINALE)"

"$PY" -m scripts.export_for_visuals --run "$RUN" --finale "$FINALE"
if [[ -f scripts/filmpack.mjs ]]; then node scripts/filmpack.mjs --out results/filmpack; fi
node scripts/build_standalone.mjs ${HEDGEFLY_HOST:+--host "$HEDGEFLY_HOST"}

git add visuals/hq/runs.json visuals/dist/hedgefly.html
if git diff --cached --quiet; then
    echo "nothing new to commit"
else
    what="$(basename "$RUN")"
    [[ -f "$FINALE/finale.json" || -f "$FINALE/finale_flies.json" ]] && what="$what and the day6_full finale"
    git commit -q -m "Refresh the visuals from $what

Written by scripts/refresh_visuals.sh, unattended, from the logs in runs/.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
    git push -q origin "$(git branch --show-current)"
    echo "committed and pushed: $(git log --oneline -1)"
fi

# The films last: they take a while, they are far too big for git (results/ is ignored), and
# they must never turn a good refresh into a failed one.
node scripts/record_hq.mjs --out results/film || echo "recording failed; the rest of the refresh stands"
node scripts/record_new.mjs --out results/film3 || echo "the new rooms did not record; the rest of the refresh stands"
