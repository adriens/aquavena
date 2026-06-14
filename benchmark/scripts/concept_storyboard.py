"""
Public-friendly storyboard version of the concept emergence timeline.

3-column "roadmap board" layout: one column per life-phase, concepts stacked
chronologically inside each column. Zero overlap possible, fully readable for
a general audience.

Inputs:
  benchmark/data/concept_emergence.json (produced by concept_emergence.py)

Outputs:
  benchmark/quarto/concept_storyboard.png
"""

from __future__ import annotations

import json
from pathlib import Path
import datetime as dt

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "concept_emergence.json"
OUT = ROOT / "quarto" / "concept_storyboard.png"

with open(SRC, "r", encoding="utf-8") as f:
    raw = json.load(f)

df = pd.DataFrame(raw["concepts"])
df["dt"] = pd.to_datetime(df["first_ts"], utc=True).dt.tz_convert("Pacific/Noumea").dt.tz_localize(None)
df = df.sort_values("dt").reset_index(drop=True)

# ── Phase definitions ──────────────────────────────────────────────────────
PHASES = [
    {
        "title":   "Phase 1",
        "subtitle":"The site is born",
        "start":   dt.datetime(2026, 5, 24),
        "end":     dt.datetime(2026, 5, 28, 23, 59),
        "tint":    "#15803d",
        "bg":      "#dcfce7",
        "blurb":   "Visually-impaired users at the centre.\n"
                   "RSS, iCal, the first MCP skill\n"
                   "and the first sketch of a robot link.",
    },
    {
        "title":   "Phase 2",
        "subtitle":"The site becomes measurable",
        "start":   dt.datetime(2026, 5, 29),
        "end":     dt.datetime(2026, 6, 12, 23, 59),
        "tint":    "#b45309",
        "bg":      "#fef3c7",
        "blurb":   "Benchmark report, Tailwind v4 migration\n"
                   "and every data-science engine\n"
                   "that powers the dashboard you read.",
    },
    {
        "title":   "Phase 3",
        "subtitle":"The site becomes agentic",
        "start":   dt.datetime(2026, 6, 13),
        "end":     dt.datetime(2026, 6, 14, 23, 59),
        "tint":    "#6d28d9",
        "bg":      "#ede9fe",
        "blurb":   "WebMCP in the browser, Reachy Mini\n"
                   "calling our tools, the universal\n"
                   "agentic-accessibility pipeline.",
    },
]

# Public-friendly labels for each concept
LABELS = {
    "WCAG fixes":         "Accessibility fixes",
    "RSS / iCal":         "RSS feeds & calendars",
    "MCP / Claude skill": "First Claude skill",
    "Reachy Mini robot":  "Robot link sketched",
    "Benchmark report":   "Benchmark PDF report",
    "Tailwind v4":        "Tailwind v3 → v4 migration",
    "Cluster drift":      "Cluster-drift maturity",
    "Markov chain":       "Workflow Markov chain",
    "Burnout detector":   "Burnout-window detector",
    "GraphSAGE GNN":      "Graph neural network",
    "Causal Impact BSTS": "Causal impact analysis",
    "Causal DAG":         "Causal DAG discovery",
    "WebMCP browser":     "WebMCP in the browser",
    "Origin Trial":       "Chrome Origin Trial token",
    "Agentic pipeline":   "Universal agentic pipeline",
}

# Bucket concepts into phases
phase_concepts = [[] for _ in PHASES]
for _, row in df.iterrows():
    for k, p in enumerate(PHASES):
        if p["start"] <= row["dt"] <= p["end"]:
            phase_concepts[k].append(row)
            break

# ── Figure ─────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(13.5, 8.5))
ax.set_xlim(0, 13.2)
# Compute max card count so y range fits the longest column (cards start at y=3.8)
max_cards = max(len(c) for c in phase_concepts)
ax.set_ylim(0, max_cards * 1.05 + 4.2)
ax.invert_yaxis()  # top = earliest in each phase
ax.axis("off")

# Three equal-width columns
col_width = 4.0
col_pad   = 0.3
COL_X = [0.2, col_width + col_pad + 0.2, 2 * (col_width + col_pad) + 0.2]
HEADER_Y = 0.6  # top of cards starts below this

for ki, phase in enumerate(PHASES):
    x0 = COL_X[ki]
    x1 = x0 + col_width

    # Phase background panel — sized to fit cards + headers comfortably
    panel = mpatches.FancyBboxPatch(
        (x0, 0.2), col_width, max_cards * 1.05 + 3.6,
        boxstyle="round,pad=0.05",
        linewidth=1.6, edgecolor=phase["tint"], facecolor=phase["bg"],
        alpha=0.92,
    )
    ax.add_patch(panel)

    # Phase header
    ax.text(x0 + col_width / 2, 0.7, phase["title"],
            ha="center", va="center",
            fontsize=11.5, fontweight="bold", color=phase["tint"])
    ax.text(x0 + col_width / 2, 1.30, phase["subtitle"],
            ha="center", va="center",
            fontsize=11, fontweight="bold", color=phase["tint"])
    # Multi-line blurb (line breaks already in the text)
    ax.text(x0 + col_width / 2, 2.30, phase["blurb"],
            ha="center", va="center",
            fontsize=8.3, style="italic", color=phase["tint"],
            linespacing=1.3)

    # Cards stacked top-to-bottom inside the column, below the blurb
    y = 3.8
    for row in phase_concepts[ki]:
        tagline = LABELS.get(row["concept"], row["concept"])
        date_str = row["dt"].strftime("%d %b")
        # Card body
        card = mpatches.FancyBboxPatch(
            (x0 + 0.25, y), col_width - 0.5, 0.85,
            boxstyle="round,pad=0.05",
            linewidth=1.2, edgecolor=phase["tint"], facecolor="white",
        )
        ax.add_patch(card)
        ax.text(x0 + 0.45, y + 0.45, tagline,
                ha="left", va="center",
                fontsize=9.2, fontweight="bold", color=phase["tint"])
        ax.text(x0 + col_width - 0.40, y + 0.45, date_str,
                ha="right", va="center",
                fontsize=8.0, color="#475569")
        y += 1.05

# Title above the panels
fig.suptitle("How the project's ideas appeared, in three life-phases",
             fontsize=13.5, fontweight="bold", y=0.99, color="#0f172a")

# Footer note
fig.text(0.5, 0.015,
         "Each card marks the first commit where the idea is visible. "
         "Coloured panels group the three life-phases the data reveals.",
         ha="center", fontsize=9, style="italic", color="#475569")

plt.tight_layout(rect=(0, 0.02, 1, 0.97))
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=180, bbox_inches="tight")
print(f"Storyboard → {OUT}")
