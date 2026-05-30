#!/usr/bin/env bash
# Replay every tagged release, build the site, and capture the real Lighthouse
# accessibility score using a temporary git worktree per tag. The current
# working tree is never touched.
#
# Output: benchmark/data/historical_scores.json
#   { "v0.1.1": 82, "v0.1.2": 86, ... }
#
# Usage: bash benchmark/scripts/replay_lighthouse.sh

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/benchmark/data/historical_scores.json"
TAGS=(v0.1.1 v0.1.2 v0.1.3 v0.1.4 v0.1.5 v1.5.0 v1.6.0 v1.7.0)
PORT=4321
WORK_BASE="$(mktemp -d -t aqv-replay-XXXX)"

cleanup() {
  for wt in "$WORK_BASE"/*; do
    [ -d "$wt" ] || continue
    git -C "$ROOT" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  done
  rmdir "$WORK_BASE" 2>/dev/null || true
}
trap cleanup EXIT

echo "Worktree base : $WORK_BASE"
echo "Output JSON   : $OUT"
mkdir -p "$(dirname "$OUT")"
echo "{" > "$OUT.tmp"
first=1

for i in "${!TAGS[@]}"; do
  tag="${TAGS[$i]}"
  wt="$WORK_BASE/$tag"
  echo
  echo ">>> [$((i+1))/${#TAGS[@]}] $tag"

  if ! git -C "$ROOT" worktree add --detach "$wt" "$tag" > /dev/null 2>&1; then
    echo "    ! worktree add failed, skipping"
    continue
  fi

  cd "$wt/site" || { echo "    ! no site/ dir"; cd "$ROOT"; continue; }

  echo "    npm install ..."
  # Use `npm install` (not `npm ci`) — historical tags sometimes have
  # package.json / package-lock.json drift that ci refuses to handle.
  if ! npm install --silent --no-audit --no-fund > /tmp/npm_${tag}.log 2>&1; then
    echo "    ! npm install failed (see /tmp/npm_${tag}.log)"
    cd "$ROOT"; continue
  fi

  echo "    build ..."
  if ! npm run build > /dev/null 2>&1; then
    echo "    ! build failed"
    cd "$ROOT"; continue
  fi

  echo "    serve + lighthouse ..."
  npx serve dist -p "$PORT" > /dev/null 2>&1 &
  SERVE_PID=$!
  sleep 3

  LH_OUT="/tmp/lh_${tag//\//_}.json"
  # Audit the Aqua-Méditerranéen menu page (same URL the production audit uses)
  npx lighthouse "http://localhost:$PORT/#aqua-m%C3%A9diterran%C3%A9en" \
    --only-categories=accessibility \
    --output=json \
    --output-path="$LH_OUT" \
    --chrome-flags="--no-sandbox --headless" \
    --quiet > /dev/null 2>&1

  kill "$SERVE_PID" 2>/dev/null
  wait "$SERVE_PID" 2>/dev/null
  sleep 1

  score="null"
  if [ -f "$LH_OUT" ]; then
    score=$(node -e "try{const lh=require('$LH_OUT');console.log(Math.round(lh.categories.accessibility.score*100));}catch(e){console.log('null');}" 2>/dev/null || echo "null")
  fi
  echo "    score : $score"

  if [ "$first" -eq 1 ]; then
    printf '  "%s": %s' "$tag" "$score" >> "$OUT.tmp"
    first=0
  else
    printf ',\n  "%s": %s' "$tag" "$score" >> "$OUT.tmp"
  fi

  cd "$ROOT"
done

printf '\n}\n' >> "$OUT.tmp"
mv "$OUT.tmp" "$OUT"

echo
echo "=== Historical scores ==="
cat "$OUT"
