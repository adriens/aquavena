#!/usr/bin/env bash
# Replay every tagged release, build the site, then run BOTH Lighthouse and
# pa11y on the same menu page. Output:
#   benchmark/data/historical_audits.json
#   { "v0.1.1": { "lighthouse": 100, "pa11y_errors": 5 }, ... }
#
# Uses git worktrees so the current working tree is never touched.
# Usage: bash benchmark/scripts/replay_audits.sh

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/benchmark/data/historical_audits.json"
TAGS=(v0.1.1 v0.1.2 v0.1.3 v0.1.4 v0.1.5 v1.5.0 v1.6.0 v1.7.0)
PORT=4321
URL="http://localhost:$PORT/#aqua-m%C3%A9diterran%C3%A9en"
WORK_BASE="$(mktemp -d -t aqv-audits-XXXX)"

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

# pa11y config (chromeLaunchConfig.args is the only way to pass --no-sandbox)
PA11Y_CONFIG="/tmp/pa11y_replay_config.json"
cat > "$PA11Y_CONFIG" <<'JSON'
{
  "standard": "WCAG2AA",
  "runners": ["htmlcs"],
  "timeout": 60000,
  "chromeLaunchConfig": {
    "args": ["--no-sandbox", "--headless", "--disable-dev-shm-usage"]
  }
}
JSON

echo "{" > "$OUT.tmp"
first=1

for i in "${!TAGS[@]}"; do
  tag="${TAGS[$i]}"
  wt="$WORK_BASE/$tag"
  echo
  echo ">>> [$((i+1))/${#TAGS[@]}] $tag"

  if ! git -C "$ROOT" worktree add --detach "$wt" "$tag" > /dev/null 2>&1; then
    echo "    ! worktree add failed"
    continue
  fi

  cd "$wt/site" || { echo "    ! no site/"; cd "$ROOT"; continue; }

  echo "    npm install ..."
  if ! npm install --silent --no-audit --no-fund > /tmp/npm_${tag}.log 2>&1; then
    echo "    ! npm install failed (see /tmp/npm_${tag}.log)"
    cd "$ROOT"; continue
  fi

  echo "    build ..."
  if ! npm run build > /tmp/build_${tag}.log 2>&1; then
    echo "    ! build failed (see /tmp/build_${tag}.log)"
    cd "$ROOT"; continue
  fi

  echo "    serve ..."
  npx serve dist -p "$PORT" > /dev/null 2>&1 &
  SERVE_PID=$!
  sleep 3

  # ── Lighthouse ───────────────────────────────────────────────────────────
  LH_OUT="/tmp/lh_${tag//\//_}.json"
  echo "    lighthouse ..."
  npx lighthouse "$URL" \
    --only-categories=accessibility \
    --output=json \
    --output-path="$LH_OUT" \
    --chrome-flags="--no-sandbox --headless" \
    --quiet > /dev/null 2>&1
  lh="null"
  if [ -f "$LH_OUT" ]; then
    lh=$(node -e "try{const r=require('$LH_OUT');console.log(Math.round(r.categories.accessibility.score*100));}catch(e){console.log('null');}" 2>/dev/null || echo "null")
  fi

  # ── pa11y (WCAG2AA, htmlcs runner) ──────────────────────────────────────
  PA_OUT="/tmp/pa_${tag//\//_}.json"
  echo "    pa11y ..."
  npx --yes pa11y "$URL" \
    --reporter json \
    --config "$PA11Y_CONFIG" \
    > "$PA_OUT" 2>/tmp/pa11y_${tag}.err || true
  pa="null"
  if [ -f "$PA_OUT" ] && [ -s "$PA_OUT" ]; then
    pa=$(node -e "try{const a=require('$PA_OUT');console.log(Array.isArray(a)?a.filter(i=>i.type==='error').length:'null');}catch(e){console.log('null');}" 2>/dev/null || echo "null")
  fi

  kill "$SERVE_PID" 2>/dev/null
  wait "$SERVE_PID" 2>/dev/null
  sleep 1

  echo "    lighthouse=$lh   pa11y_errors=$pa"

  entry="\"$tag\": { \"lighthouse\": $lh, \"pa11y_errors\": $pa }"
  if [ "$first" -eq 1 ]; then
    printf '  %s' "$entry" >> "$OUT.tmp"; first=0
  else
    printf ',\n  %s' "$entry" >> "$OUT.tmp"
  fi

  cd "$ROOT"
done

printf '\n}\n' >> "$OUT.tmp"
mv "$OUT.tmp" "$OUT"

echo
echo "=== Historical audits ==="
cat "$OUT"
