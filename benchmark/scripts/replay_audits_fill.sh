#!/usr/bin/env bash
# Fill missing per-tag accessibility scores.
#
# Replays ONLY the tags that are not yet present in
#   benchmark/data/historical_audits.json
# builds the site (bun if a bun lockfile exists, else npm), serves it, then runs
# BOTH Lighthouse and pa11y on the same menu page, and MERGES the results back
# into historical_audits.json (existing entries are preserved untouched).
#
#   { "v0.1.1": { "lighthouse": 100, "pa11y_errors": 5 }, ... }
#
# Uses git worktrees so the current working tree is never touched.
# Usage: bash benchmark/scripts/replay_audits_fill.sh
#
# Companion of replay_audits.sh (which uses a fixed representative tag list).

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/benchmark/data/historical_audits.json"
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

# ── Compute the set of tags still missing a score ──────────────────────────
ALL_TAGS=$(git -C "$ROOT" tag --sort=version:refname)
EXISTING=$(python3 -c "import json,sys;print('\n'.join(json.load(open('$OUT')).keys()))" 2>/dev/null || echo "")
MISSING=()
while IFS= read -r t; do
  [ -z "$t" ] && continue
  if ! grep -qxF "$t" <<< "$EXISTING"; then
    MISSING+=("$t")
  fi
done <<< "$ALL_TAGS"

echo "Worktree base : $WORK_BASE"
echo "Output JSON   : $OUT"
echo "Already scored: $(echo "$EXISTING" | tr '\n' ' ')"
echo "Missing tags  : ${MISSING[*]:-(none)}"
echo "Count missing : ${#MISSING[@]}"
[ "${#MISSING[@]}" -eq 0 ] && { echo "Nothing to do."; exit 0; }

mkdir -p "$(dirname "$OUT")"

# pa11y config (chromeLaunchConfig.args is the only way to pass --no-sandbox)
PA11Y_CONFIG="/tmp/pa11y_fill_config.json"
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

# Results from this run accumulate here as JSON lines: TAG\tLH\tPA
RESULTS="/tmp/aqv_fill_results.tsv"
: > "$RESULTS"

for i in "${!MISSING[@]}"; do
  tag="${MISSING[$i]}"
  wt="$WORK_BASE/${tag//\//_}"
  echo
  echo ">>> [$((i+1))/${#MISSING[@]}] $tag"

  if ! git -C "$ROOT" worktree add --detach "$wt" "$tag" > /dev/null 2>&1; then
    echo "    ! worktree add failed"; continue
  fi

  cd "$wt/site" 2>/dev/null || { echo "    ! no site/"; cd "$ROOT"; continue; }

  # Pick package manager based on lockfile present at that tag
  if [ -f bun.lock ] || [ -f bun.lockb ]; then PM=bun; else PM=npm; fi
  echo "    install ($PM) ..."
  if [ "$PM" = bun ]; then
    bun install --silent > /tmp/inst_${tag//\//_}.log 2>&1 || { echo "    ! bun install failed"; cd "$ROOT"; continue; }
    echo "    build ..."
    bun run build > /tmp/build_${tag//\//_}.log 2>&1 || { echo "    ! build failed (see /tmp/build_${tag//\//_}.log)"; cd "$ROOT"; continue; }
  else
    npm install --legacy-peer-deps --silent --no-audit --no-fund > /tmp/inst_${tag//\//_}.log 2>&1 || { echo "    ! npm install failed"; cd "$ROOT"; continue; }
    echo "    build ..."
    npm run build > /tmp/build_${tag//\//_}.log 2>&1 || { echo "    ! build failed (see /tmp/build_${tag//\//_}.log)"; cd "$ROOT"; continue; }
  fi

  echo "    serve ..."
  npx --yes serve dist -p "$PORT" > /dev/null 2>&1 &
  SERVE_PID=$!
  sleep 3

  LH_OUT="/tmp/lh_${tag//\//_}.json"
  echo "    lighthouse ..."
  npx --yes lighthouse "$URL" \
    --only-categories=accessibility \
    --output=json \
    --output-path="$LH_OUT" \
    --chrome-flags="--no-sandbox --headless" \
    --quiet > /dev/null 2>&1
  lh="null"
  if [ -f "$LH_OUT" ]; then
    lh=$(node -e "try{const r=require('$LH_OUT');console.log(Math.round(r.categories.accessibility.score*100));}catch(e){console.log('null');}" 2>/dev/null || echo "null")
  fi

  PA_OUT="/tmp/pa_${tag//\//_}.json"
  echo "    pa11y ..."
  npx --yes pa11y "$URL" \
    --reporter json \
    --config "$PA11Y_CONFIG" \
    > "$PA_OUT" 2>/tmp/pa11y_${tag//\//_}.err || true
  pa="null"
  if [ -f "$PA_OUT" ] && [ -s "$PA_OUT" ]; then
    pa=$(node -e "try{const a=require('$PA_OUT');console.log(Array.isArray(a)?a.filter(i=>i.type==='error').length:'null');}catch(e){console.log('null');}" 2>/dev/null || echo "null")
  fi

  kill "$SERVE_PID" 2>/dev/null
  wait "$SERVE_PID" 2>/dev/null
  sleep 1

  echo "    lighthouse=$lh   pa11y_errors=$pa"
  printf '%s\t%s\t%s\n' "$tag" "$lh" "$pa" >> "$RESULTS"

  cd "$ROOT"
done

# ── Merge new results into historical_audits.json (preserve existing) ───────
echo
echo "=== Merging into $OUT ==="
python3 - "$OUT" "$RESULTS" <<'PY'
import json, sys
out_path, res_path = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(out_path))
except Exception:
    data = {}
added = 0
with open(res_path) as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        tag, lh, pa = line.split("\t")
        lh = None if lh in ("null", "") else int(lh)
        pa = None if pa in ("null", "") else int(pa)
        # Only record tags where at least lighthouse succeeded
        if lh is None and pa is None:
            continue
        data[tag] = {"lighthouse": lh, "pa11y_errors": pa}
        added += 1

# Sort keys by semver for readability
def semkey(t):
    import re
    nums = re.findall(r"\d+", t)
    return [int(n) for n in nums] if nums else [0]
ordered = {k: data[k] for k in sorted(data, key=semkey)}
json.dump(ordered, open(out_path, "w"), indent=2)
open(out_path, "a").write("\n")
print(f"Merged {added} new tag(s); total now {len(ordered)}.")
PY

echo
echo "=== historical_audits.json (final) ==="
cat "$OUT"
