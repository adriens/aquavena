# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "sentence-transformers>=3.0,<4",
#   "numpy>=1.26",
#   "pandas>=2.0",
#   "duckdb>=1.0",
#   "matplotlib>=3.8",
# ]
# ///
"""
Galactic commit-similarity matrix.

A second view of the very same commit-similarity graph: instead of a spatial
node-link layout (ForceAtlas2), the full 179x179 cosine-similarity matrix is
rendered as a dark "galactic" heatmap. Rows/columns are ordered by semantic
cluster, then chronologically inside each cluster, so:

  - bright diagonal blocks   = cohesive clusters
  - tiny blinding-white block = the near-identical merge commits
  - off-diagonal glow         = bridges / semantic bleed between themes

The similarity is recomputed from scratch (re-embedding every commit subject
with BAAI/bge-m3) so the matrix is dense and continuous, not the thresholded
graph edges.

Input  : benchmark/data/benchmark.duckdb  (commit_classification)
Output : benchmark/quarto/similarity_matrix.png

Usage  : uv run --script benchmark/scripts/similarity_matrix.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "benchmark.duckdb"
OUT = ROOT / "quarto" / "similarity_matrix.png"

BG = "#0A0E1A"        # deep space navy (matches the galactic cover)
CLUSTER_COLOURS = ["#5eead4", "#f87171", "#38bdf8", "#c084fc", "#fbbf24", "#34d399"]

# ── 1. Pull commits, ordered by cluster then time ──────────────────────────
con = duckdb.connect(str(DB), read_only=True)
df = con.execute("""
    SELECT cc.git_sha, cc.subject, cc.cluster_id, gc.commit_ts
    FROM commit_classification cc
    JOIN git_commits gc USING (git_sha)
    WHERE cc.subject IS NOT NULL
""").fetchdf()
con.close()

df["commit_ts"] = pd.to_datetime(df["commit_ts"], utc=True)
df = df.sort_values(["cluster_id", "commit_ts"]).reset_index(drop=True)
n = len(df)
print(f"{n} commits, {df.cluster_id.nunique()} clusters")

# ── 2. Re-embed subjects and build the full cosine matrix ──────────────────
print("Loading BAAI/bge-m3 (cached if already downloaded)…")
model = SentenceTransformer("BAAI/bge-m3")
emb = model.encode(df["subject"].tolist(), normalize_embeddings=True,
                   show_progress_bar=False)
sim = emb @ emb.T            # cosine, since rows are L2-normalised
np.fill_diagonal(sim, 1.0)

# Cluster block boundaries (for separators + ribbons)
sizes = df.groupby("cluster_id").size().sort_index()
bounds = np.cumsum(sizes.values)
starts = np.concatenate([[0], bounds[:-1]])

# ── 3. Galactic colormap: navy → teal → white ──────────────────────────────
cmap = LinearSegmentedColormap.from_list(
    "galaxy", [BG, "#0f766e", "#2dd4bf", "#a7f3d0", "#ffffff"])
# Stretch contrast: most off-diagonal sim sits ~0.3-0.6
vmin = float(np.percentile(sim[~np.eye(n, dtype=bool)], 35))

# ── 4. Plot ─────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(8.2, 8.2), facecolor=BG)
# main matrix axes, leaving a thin margin for the cluster ribbons
left, bottom, w, h, rib = 0.10, 0.06, 0.84, 0.84, 0.022
ax = fig.add_axes([left + rib, bottom, w - rib, h - rib])
ax.set_facecolor(BG)

im = ax.imshow(sim, cmap=cmap, vmin=vmin, vmax=1.0,
               interpolation="nearest", origin="upper", aspect="equal")

# faint separators between cluster blocks
for b in bounds[:-1]:
    ax.axhline(b - 0.5, color="#1e293b", linewidth=0.6)
    ax.axvline(b - 0.5, color="#1e293b", linewidth=0.6)

ax.set_xticks([]); ax.set_yticks([])
for s in ax.spines.values():
    s.set_visible(False)

# cluster ribbons: left column + top row
ax_left = fig.add_axes([left, bottom, rib, h - rib])
ax_top = fig.add_axes([left + rib, bottom + h - rib, w - rib, rib])
for a in (ax_left, ax_top):
    a.set_facecolor(BG); a.set_xticks([]); a.set_yticks([])
    for s in a.spines.values():
        s.set_visible(False)
for cid, s0, s1 in zip(sizes.index, starts, bounds):
    col = CLUSTER_COLOURS[cid % len(CLUSTER_COLOURS)]
    ax_left.axhspan(s0, s1, color=col)
    ax_top.axvspan(s0, s1, color=col)
    mid = (s0 + s1) / 2
    ax_left.text(-0.6, mid, f"C{cid}", color=col, fontsize=8,
                 ha="right", va="center", fontweight="bold")
ax_left.set_ylim(n, 0); ax_top.set_xlim(0, n)

# colourbar
cax = fig.add_axes([left + rib, bottom - 0.035, w - rib, 0.012])
cb = fig.colorbar(im, cax=cax, orientation="horizontal")
cb.set_label("cosine similarity of commit messages (BAAI/bge-m3)",
             color="#cbd5e1", fontsize=8)
cb.ax.tick_params(colors="#cbd5e1", labelsize=7)
cb.outline.set_visible(False)

fig.text(left, bottom + h + 0.025,
         "Commit-similarity matrix — galactic view",
         color="#f1f5f9", fontsize=14, fontweight="bold")
fig.text(left, bottom + h + 0.005,
         "179×179 cosine similarity · ordered by semantic cluster, then time · "
         "bright blocks = cohesive clusters, off-diagonal glow = bridges",
         color="#94a3b8", fontsize=8.5)

fig.savefig(OUT, dpi=150, facecolor=BG, bbox_inches="tight")
print(f"Figure → {OUT}")
