#!/usr/bin/env bash
# Validate HTML quality of both sites against the W3C Nu HTML validator
# AND measure page weight via Lighthouse's `total-byte-weight` performance audit.
#
# Output: benchmark/data/html_validation.json
#   { "aquavena.nc": {"errors": N, "warnings": M, "bytes": N},
#     "our-site":    {"errors": N, "warnings": M, "bytes": N} }
#
# Requirements: curl, jq, node, npx (lighthouse). Site built (site/dist).

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/benchmark/data/html_validation.json"
mkdir -p "$(dirname "$OUT")"

VALIDATOR="https://validator.w3.org/nu/?out=json"
UA="Mozilla/5.0 aquavena-benchmark/1.0"

count_errors() {   jq '[.messages[]? | select(.type == "error")] | length'  ; }
count_warnings() { jq '[.messages[]? | select(.type == "info" and .subType == "warning")] | length' ; }

# ── aquavena.nc (validate via remote URL) ─────────────────────────────────
echo "Validating aquavena.nc menu page ..."
NC_URL="https://www.aquavena.nc/formules/aqua-m%C3%A9diterran%C3%A9en"
NC_JSON="/tmp/htmlval_nc.json"
curl -s -A "$UA" "${VALIDATOR}&doc=${NC_URL}" > "$NC_JSON"
nc_e=$(count_errors   < "$NC_JSON")
nc_w=$(count_warnings < "$NC_JSON")
echo "  errors=$nc_e  warnings=$nc_w"

# ── Our site (serve dist, fetch HTML, POST to validator) ──────────────────
echo "Starting local server for our site ..."
PORT=4321
(cd "$ROOT/site" && npx serve dist -p $PORT > /dev/null 2>&1) &
SERVE_PID=$!
trap "kill $SERVE_PID 2>/dev/null || true" EXIT
sleep 3

echo "Validating our site homepage ..."
OUR_HTML="/tmp/our_home.html"
curl -s "http://localhost:$PORT/" > "$OUR_HTML"
OUR_JSON="/tmp/htmlval_ours.json"
curl -s -A "$UA" \
  -X POST \
  -H "Content-Type: text/html; charset=utf-8" \
  --data-binary @"$OUR_HTML" \
  "${VALIDATOR}" > "$OUR_JSON"
o_e=$(count_errors   < "$OUR_JSON")
o_w=$(count_warnings < "$OUR_JSON")
echo "  errors=$o_e  warnings=$o_w"

# ── Page weight via Lighthouse performance audit ──────────────────────────
extract_bytes() {
  # Lighthouse `total-byte-weight` audit reports total transferred bytes
  node -e "try{const r=require('$1');console.log(Math.round(r.audits['total-byte-weight'].numericValue));}catch(e){console.log('null');}" 2>/dev/null || echo "null"
}

echo "Measuring aquavena.nc page weight (Lighthouse performance) ..."
NC_PERF_JSON="/tmp/lh_perf_nc.json"
npx lighthouse "$NC_URL" \
  --only-categories=performance \
  --output=json --output-path="$NC_PERF_JSON" \
  --chrome-flags="--no-sandbox --headless" \
  --quiet > /dev/null 2>&1
nc_bytes=$(extract_bytes "$NC_PERF_JSON")
echo "  bytes=$nc_bytes"

echo "Measuring our site page weight ..."
OUR_PERF_JSON="/tmp/lh_perf_ours.json"
npx lighthouse "http://localhost:$PORT/" \
  --only-categories=performance \
  --output=json --output-path="$OUR_PERF_JSON" \
  --chrome-flags="--no-sandbox --headless" \
  --quiet > /dev/null 2>&1
o_bytes=$(extract_bytes "$OUR_PERF_JSON")
echo "  bytes=$o_bytes"

# ── Write JSON ────────────────────────────────────────────────────────────
cat > "$OUT" <<EOF
{
  "aquavena.nc": { "errors": ${nc_e}, "warnings": ${nc_w}, "bytes": ${nc_bytes} },
  "our-site":    { "errors": ${o_e}, "warnings": ${o_w}, "bytes": ${o_bytes} }
}
EOF

echo
echo "=== HTML validation summary ==="
cat "$OUT"
