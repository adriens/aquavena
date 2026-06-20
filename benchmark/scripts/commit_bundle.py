# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "networkx>=3.2",
#   "numpy>=1.26",
#   "matplotlib>=3.8",
# ]
# ///
"""
Hierarchical-edge-bundling view of the commit-similarity graph.

A third, artistic view of the same graph: the 179 commits are placed on a
circle, grouped by semantic cluster (coloured arcs on the rim), and every
similarity edge (cosine >= 0.55) is drawn as a spline that bows toward the
centre. Bundles that form between two arcs show which themes "talk" to each
other; an arc with almost no outgoing bundle (the merge commits) is a theme
that stands alone.

Input  : benchmark/data/commit_graph.gexf
Output : benchmark/quarto/commit_bundle.png

Usage  : uv run --script benchmark/scripts/commit_bundle.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib.patches import PathPatch, Wedge
from matplotlib.path import Path as MplPath

ROOT = Path(__file__).resolve().parents[1]
GEXF = ROOT / "data" / "commit_graph.gexf"
OUT = ROOT / "quarto" / "commit_bundle.png"

BG = "#0A0E1A"
CLUSTER_COLOURS = ["#5eead4", "#f87171", "#38bdf8", "#c084fc", "#fbbf24", "#34d399"]
R = 1.0            # node ring radius
BETA = 0.36        # bundling strength: control points pulled toward centre

G = nx.read_gexf(GEXF)

# ── Order nodes by cluster, then chronologically inside the cluster ────────
def ts(n):
    return G.nodes[n].get("timestamp", "")

nodes = sorted(G.nodes(), key=lambda n: (int(G.nodes[n]["cluster"]), ts(n)))
n = len(nodes)
idx = {nd: i for i, nd in enumerate(nodes)}

# angle: start at top (90°), go clockwise
ang = {nd: np.deg2rad(90 - 360 * i / n) for i, nd in enumerate(nodes)}
pos = {nd: np.array([R * np.cos(a), R * np.sin(a)]) for nd, a in ang.items()}
clu = {nd: int(G.nodes[nd]["cluster"]) for nd in nodes}
pr = {nd: float(G.nodes[nd].get("pagerank", 0.0)) for nd in nodes}

# ── Figure ──────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8.2, 8.6), facecolor=BG)
ax.set_facecolor(BG)
ax.set_xlim(-1.45, 1.45); ax.set_ylim(-1.5, 1.55)
ax.set_aspect("equal"); ax.axis("off")

# ── Bundled edges (drawn first, behind nodes) ──────────────────────────────
wts = np.array([float(d["weight"]) for _, _, d in G.edges(data=True)])
wmin, wmax = wts.min(), wts.max()
# stronger edges → brighter; sort so bright edges draw on top
edges = sorted(G.edges(data=True), key=lambda e: float(e[2]["weight"]))
for u, v, d in edges:
    w = float(d["weight"])
    p0, p3 = pos[u], pos[v]
    c1, c2 = p0 * BETA, p3 * BETA            # pull control points to centre
    t = (w - wmin) / (wmax - wmin + 1e-9)
    alpha = 0.04 + 0.42 * t ** 1.6
    lw = 0.3 + 0.9 * t
    col = CLUSTER_COLOURS[clu[u] % 6]
    path = MplPath([p0, c1, c2, p3],
                   [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4])
    ax.add_patch(PathPatch(path, facecolor="none", edgecolor=col,
                           linewidth=lw, alpha=alpha, capstyle="round"))

# ── Nodes (size ∝ PageRank) ────────────────────────────────────────────────
pr_vals = np.array(list(pr.values()))
pr_lo, pr_hi = pr_vals.min(), pr_vals.max()
for nd in nodes:
    p = pos[nd]
    s = 6 + 90 * ((pr[nd] - pr_lo) / (pr_hi - pr_lo + 1e-9)) ** 0.8
    ax.scatter(*p, s=s, c=CLUSTER_COLOURS[clu[nd] % 6],
               edgecolors="white", linewidths=0.25, zorder=3, alpha=0.95)

# ── Cluster arcs on the rim + labels ───────────────────────────────────────
from itertools import groupby
order = nodes
i = 0
for cid, grp in groupby(order, key=lambda nd: clu[nd]):
    grp = list(grp)
    a0 = 90 - 360 * (i) / n
    a1 = 90 - 360 * (i + len(grp)) / n
    # Wedge wants angles increasing CCW; we go clockwise so swap
    ax.add_patch(Wedge((0, 0), R * 1.20, a1, a0, width=R * 0.05,
                       facecolor=CLUSTER_COLOURS[cid % 6], edgecolor="none", alpha=0.95))
    amid = np.deg2rad((a0 + a1) / 2)
    lr = R * 1.34
    ax.text(lr * np.cos(amid), lr * np.sin(amid), f"C{cid}",
            color=CLUSTER_COLOURS[cid % 6], fontsize=11, fontweight="bold",
            ha="center", va="center")
    i += len(grp)

ax.text(0, 1.50, "Commit-similarity bundle — who talks to whom",
        color="#f1f5f9", fontsize=14, fontweight="bold", ha="center")
ax.text(0, 1.42,
        "179 commits on the rim, grouped by semantic cluster · each spline = a "
        "cosine-similarity ≥ 0.55 link, bowed toward the centre",
        color="#94a3b8", fontsize=8.3, ha="center")

fig.savefig(OUT, dpi=150, facecolor=BG, bbox_inches="tight")
print(f"{n} nodes · {G.number_of_edges()} edges → {OUT}")
