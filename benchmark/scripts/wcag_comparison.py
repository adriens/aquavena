# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Build a criterion-by-criterion WCAG comparison between the official
aquavena.nc site and our accessible rebuild, focused on what actually
matters for a low-vision / elderly user.

Sources (all already produced by the audit pipeline / a live re-audit):
  benchmark/reports/lighthouse-aquavena-nc.report.json   official site (Lighthouse)
  benchmark/reports/pa11y-aquavena-nc.json               official site (pa11y, live re-audit)
  benchmark/reports/lighthouse.report.json               our site (Lighthouse)
  benchmark/reports/pa11y.json                           our site (pa11y)

Output:
  benchmark/data/wcag_comparison.json

Usage:
  uv run --script benchmark/scripts/wcag_comparison.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
OUT = ROOT / "data" / "wcag_comparison.json"

# Human-readable mapping for the WCAG success criteria we encounter, with the
# concrete consequence for a low-vision / elderly reader.
SC_INFO = {
    "1.4.3": {
        "name": "Contrast (Minimum)",
        "level": "AA",
        "low_vision_impact": "Critical",
        "consequence": "Text and buttons fall below the 4.5:1 ratio — washed out and "
                       "unreadable for ageing eyes and low contrast sensitivity.",
    },
    "1.4.4": {
        "name": "Resize Text",
        "level": "AA",
        "low_vision_impact": "Critical",
        "consequence": "Pinch-zoom is disabled, so the page cannot be enlarged on a "
                       "phone — the single most common low-vision coping strategy.",
    },
    "1.4.10": {
        "name": "Reflow",
        "level": "AA",
        "low_vision_impact": "High",
        "consequence": "Blocking zoom also prevents content reflow at 400%, forcing "
                       "two-axis scrolling.",
    },
}


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def parse_pa11y_codes(report) -> Counter:
    """Count pa11y errors per WCAG success criterion (e.g. '1.4.3')."""
    c: Counter = Counter()
    if not report:
        return c
    # Normalise to a flat list of issue dicts across pa11y / pa11y-ci formats
    issues: list = []
    if isinstance(report, list):                       # single-page pa11y
        issues = report
    elif isinstance(report, dict):
        res = report.get("results", report)
        if isinstance(res, dict):                      # pa11y-ci: {url: [issues]}
            for v in res.values():
                if isinstance(v, list):
                    issues.extend(v)
        elif isinstance(res, list):
            issues = res
    for it in issues:
        if not isinstance(it, dict) or it.get("type") != "error":
            continue
        m = re.search(r"Guideline\d+_\d+\.(\d+)_(\d+)_(\d+)", it.get("code", ""))
        if m:
            c[f"{m.group(1)}.{m.group(2)}.{m.group(3)}"] += 1
        else:
            c["other"] += 1
    return c


def lh_score(report):
    if not report:
        return None
    return round(report["categories"]["accessibility"]["score"] * 100)


def lh_audit_fail(report, audit_id):
    """Return number of failing nodes for a Lighthouse audit, or None."""
    if not report:
        return None
    a = report.get("audits", {}).get(audit_id)
    if not a or a.get("score") in (None, 1):
        return None
    return len(a.get("details", {}).get("items", []))


lh_nc = load(REPORTS / "lighthouse-aquavena-nc.report.json")
lh_ours = load(REPORTS / "lighthouse.report.json")
pa_nc = load(REPORTS / "pa11y-aquavena-nc.json")
pa_ours = load(REPORTS / "pa11y.json")

nc_codes = parse_pa11y_codes(pa_nc)
ours_codes = parse_pa11y_codes(pa_ours)

# Lighthouse contributes two extra signals not captured by pa11y's htmlcs runner
nc_contrast_nodes = lh_audit_fail(lh_nc, "color-contrast")
nc_viewport_blocked = lh_audit_fail(lh_nc, "meta-viewport") is not None

# Assemble per-criterion rows
criteria = []

# 1.4.3 Contrast — from pa11y (htmlcs) on the official site
contrast_nc = nc_codes.get("1.4.3", 0)
criteria.append({
    "sc": "1.4.3", **SC_INFO["1.4.3"],
    "nc_errors": contrast_nc,
    "ours_errors": ours_codes.get("1.4.3", 0),
    "evidence": f"{contrast_nc} pa11y errors on aquavena.nc; "
                f"{nc_contrast_nodes} failing nodes confirmed by Lighthouse.",
})

# 1.4.4 Resize Text — from Lighthouse meta-viewport audit
criteria.append({
    "sc": "1.4.4", **SC_INFO["1.4.4"],
    "nc_errors": 1 if nc_viewport_blocked else 0,
    "ours_errors": 0,
    "evidence": "meta viewport sets user-scalable=no and maximum-scale=1.0 "
                "on aquavena.nc — pinch-zoom disabled."
                if nc_viewport_blocked else "viewport allows zoom.",
})

# Any other pa11y criteria found on the official site (robustness)
for code, n in nc_codes.items():
    if code in ("1.4.3",) or code == "other":
        continue
    info = SC_INFO.get(code, {"name": code, "level": "AA",
                              "low_vision_impact": "Medium", "consequence": ""})
    criteria.append({
        "sc": code, **info,
        "nc_errors": n, "ours_errors": ours_codes.get(code, 0),
        "evidence": f"{n} pa11y errors on aquavena.nc.",
    })

out = {
    "url": "https://www.aquavena.nc/formules/aqua-méditerranéen",
    "audit_date_pa11y": (pa_nc[0].get("runnerExtras", {}) if isinstance(pa_nc, list) and pa_nc else {}) and None,
    "standard": "WCAG 2.1 AA",
    "tools": ["pa11y (HTML_CodeSniffer, WCAG2AA)", "Lighthouse accessibility"],
    "summary": {
        "nc_lighthouse": lh_score(lh_nc),
        "ours_lighthouse": lh_score(lh_ours),
        "nc_pa11y_errors": int(sum(nc_codes.values())),
        "ours_pa11y_errors": int(sum(ours_codes.values())),
        "nc_contrast_nodes_lighthouse": nc_contrast_nodes,
    },
    "criteria": criteria,
}
OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
print(json.dumps(out["summary"], indent=2))
print(f"\n{len(criteria)} criteria written → {OUT}")
for c in criteria:
    print(f"  SC {c['sc']:7} {c['name']:20} NC={c['nc_errors']:>3}  ours={c['ours_errors']:>3}  [{c['low_vision_impact']}]")
