#!/usr/bin/env bash
# Run the privacy audit on both sites, write a compact summary JSON.
#
# Output: benchmark/data/privacy_audit.json
#   { "aquavena.nc": {...}, "our-site": {...} }
#
# Requires: site already built (site/dist).

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/benchmark/data/privacy_audit.json"
SCRIPT="$ROOT/benchmark/scripts/audit_privacy.mjs"

NC_URL="https://www.aquavena.nc/formules/aqua-m%C3%A9diterran%C3%A9en"
PORT=4321
OUR_URL="http://localhost:$PORT/"

echo "Output: $OUT"
mkdir -p "$(dirname "$OUT")"

# Start local server for our site
echo "Starting local server ..."
(cd "$ROOT/site" && npx serve dist -p $PORT > /dev/null 2>&1) &
SERVE_PID=$!
trap "kill $SERVE_PID 2>/dev/null || true" EXIT
sleep 3

# Install puppeteer locally if needed
if [ ! -d "$ROOT/benchmark/scripts/node_modules/puppeteer" ]; then
  echo "Installing puppeteer (one-time) ..."
  ( cd "$ROOT/benchmark/scripts" && npm install --silent --no-audit --no-fund > /dev/null 2>&1 )
fi

echo "Running privacy audit (puppeteer) ..."
RAW="/tmp/privacy_raw.json"
( cd "$ROOT/benchmark/scripts" && \
  node "$SCRIPT" "$NC_URL" "$OUR_URL" > "$RAW" )

# Re-key by short site label
node -e "
const raw = require('$RAW');
const out = {};
for (const [u, v] of Object.entries(raw)) {
  const key = u.includes('aquavena.nc') ? 'aquavena.nc' : 'our-site';
  out[key] = {
    total_requests:       v.total_requests       ?? null,
    third_party_requests: v.third_party_requests ?? null,
    third_party_hosts:    v.third_party_hosts    ?? [],
    known_trackers:       v.known_trackers       ?? [],
    cookies_count:        v.cookies_count        ?? null,
    cookies:              v.cookies              ?? []
  };
}
require('fs').writeFileSync('$OUT', JSON.stringify(out, null, 2));
console.log(JSON.stringify(out, null, 2));
"
