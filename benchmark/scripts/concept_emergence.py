"""
Concept emergence timeline.

For each "key concept" of the project (WebMCP, Reachy Mini, BSTS, GraphSAGE,
…), find the EARLIEST commit whose embedding is closest to that concept
description.  The result is a chronological timeline showing when each idea
first surfaced in the codebase — purely from semantic distance on the
existing BAAI/bge-m3 embeddings, no manual annotation.

Inputs:
  benchmark/data/commit_semantics.json   (commits with cluster, ts, subject, embedding 2D)

Outputs:
  benchmark/quarto/concept_emergence.png  timeline visualisation
  benchmark/data/concept_emergence.json   first-mention table
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "benchmark.duckdb"
OUT_PNG = ROOT / "quarto" / "concept_emergence.png"
OUT_JSON = ROOT / "data" / "concept_emergence.json"

# ── 1. The concepts whose emergence we want to date ─────────────────────────
# Each entry: (short name, full description used for embedding)
CONCEPTS = [
    ("WCAG fixes",       "Fix accessibility contrast and pa11y WCAG 2.1 AA errors"),
    ("Benchmark report", "Build the Quarto PDF benchmark report with charts"),
    ("Tailwind v4",      "Migrate Tailwind CSS from version 3 to version 4"),
    ("MCP / Claude skill", "Claude Code MCP server skill for menus on Hugging Face"),
    ("RSS / iCal",       "RSS feeds and iCal calendars per regime"),
    ("WebMCP browser",   "WebMCP API navigator.modelContext tool registration in browser"),
    ("Reachy Mini robot", "Reachy Mini robot calls Aquavena MCP tools to read menus aloud"),
    ("Causal Impact BSTS", "Bayesian structural time series CausalImpact for intervention effects"),
    ("GraphSAGE GNN",    "GraphSAGE graph neural network predicting commit clusters"),
    ("Cluster drift",    "Cluster drift maturity signal across release timeline"),
    ("Markov chain",     "Markov transition matrix between commit semantic clusters"),
    ("Burnout detector", "Burnout window detector friction signal from token telemetry"),
    ("Causal DAG",       "Causal DAG discovery via PC algorithm conditional independence"),
    ("Origin Trial",     "Chrome Origin Trial token for WebMCP in HTML head"),
    ("Agentic pipeline", "Universal agentic accessibility pipeline AI agents specialised"),
]

# ── 2. Load commit history with subjects + timestamps ──────────────────────
con = duckdb.connect(str(DB), read_only=True)
commits = con.execute("""
SELECT gc.git_sha, gc.commit_ts, gc.subject, cc.cluster_id
FROM git_commits gc
JOIN commit_classification cc USING (git_sha)
WHERE gc.commit_ts IS NOT NULL AND gc.subject IS NOT NULL
ORDER BY gc.commit_ts
""").fetchdf()
commits["commit_ts"] = pd.to_datetime(commits["commit_ts"], utc=True).dt.tz_convert("Pacific/Noumea")
print(f"Loaded {len(commits)} commits")

# ── 3. Embed everything with the same model used elsewhere ─────────────────
print("Loading BAAI/bge-m3 (cached if previously downloaded)…")
model = SentenceTransformer("BAAI/bge-m3", trust_remote_code=False)

print("Embedding concepts…")
concept_emb  = model.encode([c[1] for c in CONCEPTS], normalize_embeddings=True)
print("Embedding commits…")
commit_emb   = model.encode(commits["subject"].tolist(), normalize_embeddings=True,
                            show_progress_bar=True, batch_size=32)

# ── 4. For each concept, find the EARLIEST commit above a similarity floor ─
SIM_FLOOR = 0.55  # below this we don't claim the concept is present
sim = cosine_similarity(concept_emb, commit_emb)

results = []
for idx, (name, desc) in enumerate(CONCEPTS):
    row = sim[idx]
    # Indices of commits above the floor, ordered chronologically (already done)
    above = np.where(row >= SIM_FLOOR)[0]
    if len(above) == 0:
        # Fall back to the single most similar commit, even if below the floor
        best_idx = int(np.argmax(row))
        first_idx = best_idx
        flag = "below-floor"
    else:
        first_idx = int(above[0])
        flag = "ok"
    c = commits.iloc[first_idx]
    results.append({
        "concept": name,
        "description": desc,
        "first_ts": c["commit_ts"].isoformat(),
        "first_sha": c["git_sha"],
        "first_subject": c["subject"],
        "similarity": float(row[first_idx]),
        "matches_above_floor": int(len(above)),
        "flag": flag,
        "cluster_id": int(c["cluster_id"]) if pd.notna(c["cluster_id"]) else None,
    })
    print(f"  {name:22s} → {c['commit_ts'].strftime('%d %b %H:%M')} "
          f"(sim={row[first_idx]:.2f})  {c['subject'][:55]}")

# ── 5. Render the timeline ─────────────────────────────────────────────────
df = pd.DataFrame(results)
df["dt"] = pd.to_datetime(df["first_ts"])
df = df.sort_values("dt").reset_index(drop=True)

fig, ax = plt.subplots(figsize=(12, 6.5))

# Multi-level vertical placement to avoid overlaps when concepts cluster in time
# Strategy: walk chronologically; for each label, find the lowest available
# level (alternating top/bottom) that doesn't overlap a recently used one.
LEVELS_TOP = [1.0, 1.55, 2.10]
LEVELS_BOT = [-1.0, -1.55, -2.10]
MIN_SPACING = pd.Timedelta(hours=8)

used_top = []  # list of (dt, level_idx)
used_bot = []

ys = []
for i, row in df.iterrows():
    side = "top" if i % 2 == 0 else "bot"
    # Drop expired entries (further away than MIN_SPACING)
    if side == "top":
        used_top = [(t, lv) for t, lv in used_top if row["dt"] - t < MIN_SPACING]
        taken = {lv for _, lv in used_top}
        free_levels = [j for j in range(len(LEVELS_TOP)) if j not in taken]
        if not free_levels:  # all top levels busy → flip to bottom
            side = "bot"
        else:
            lv = free_levels[0]
            ys.append(LEVELS_TOP[lv])
            used_top.append((row["dt"], lv))
            continue
    # bottom path
    used_bot = [(t, lv) for t, lv in used_bot if row["dt"] - t < MIN_SPACING]
    taken = {lv for _, lv in used_bot}
    free_levels = [j for j in range(len(LEVELS_BOT)) if j not in taken]
    if not free_levels:
        # last resort: stack on top of the most recent same-side label
        lv = len(LEVELS_BOT) - 1
    else:
        lv = free_levels[0]
    ys.append(LEVELS_BOT[lv])
    used_bot.append((row["dt"], lv))

for i, row in df.iterrows():
    y = ys[i]
    colour = "#dc2626" if row["flag"] == "below-floor" else "#0f766e"
    ax.plot([row["dt"], row["dt"]], [0, y], color=colour, linewidth=1.0, alpha=0.5)
    ax.scatter([row["dt"]], [y], s=70, color=colour, zorder=3,
               edgecolor="white", linewidth=1.2)
    ax.text(row["dt"], y + (0.16 if y > 0 else -0.16),
            f"{row['concept']}\nsim={row['similarity']:.2f}",
            ha="center", va="bottom" if y > 0 else "top",
            fontsize=7.5, fontweight="bold",
            color=colour, linespacing=1.0)

# Centre timeline
ax.axhline(0, color="#475569", linewidth=1.4)
ax.scatter(df["dt"], [0] * len(df), s=14, color="#475569", zorder=3)

# Format dates
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))
ax.set_xlim(df["dt"].min() - pd.Timedelta(hours=8),
            df["dt"].max() + pd.Timedelta(hours=8))
ax.set_ylim(-3.0, 3.0)
ax.set_yticks([])
ax.set_xlabel("First mention (commit timestamp, Pacific/Noumea)")
for s in ("left", "right", "top"):
    ax.spines[s].set_visible(False)
ax.set_title("Concept emergence timeline — when each idea first surfaced in commits",
             fontsize=12, fontweight="bold", pad=8)
ax.text(0.5, -0.12,
        "Teal = first commit above cosine-similarity floor 0.55  ·  "
        "Red = best match below the floor (concept named only later, "
        "earliest sibling commit shown)",
        transform=ax.transAxes, ha="center", fontsize=8,
        style="italic", color="#475569")

plt.tight_layout()
OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT_PNG, dpi=160, bbox_inches="tight")
print(f"\nFigure  → {OUT_PNG}")

# ── 6. Save JSON ───────────────────────────────────────────────────────────
summary = {
    "n_commits_searched": len(commits),
    "n_concepts": len(CONCEPTS),
    "similarity_floor": SIM_FLOOR,
    "model": "BAAI/bge-m3 (normalised, cosine)",
    "concepts": results,
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"Summary → {OUT_JSON}")
