"""
Causal DAG discovery on commit-level features using PC algorithm.

Goal: instead of asking "what is the effect of intervention X?" (CausalImpact)
we ask "what causes what in this system?" — the algorithm has to find the
directed acyclic graph of conditional dependencies, on its own.

Method:
- 146 commits × ~10 features (graph-position, commit type, temporal, usage)
- PC algorithm (Peter-Clark, 1991) with Fisher's Z conditional-independence test
- alpha = 0.05 for edge significance

Outputs:
  benchmark/quarto/causal_dag.png      DAG visualisation
  benchmark/data/causal_dag.json       edges + metadata
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from causallearn.search.ConstraintBased.PC import pc
from causallearn.utils.cit import fisherz

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "benchmark.duckdb"
OUT_PNG = ROOT / "quarto" / "causal_dag.png"
OUT_JSON = ROOT / "data" / "causal_dag.json"

# ── 1. Pull commit-level data with all candidate features ──────────────────
con = duckdb.connect(str(DB), read_only=True)
df = con.execute("""
WITH tok AS (
  SELECT git_sha,
         SUM(total_tokens)                                                AS tokens,
         SUM(CASE WHEN model LIKE '%opus%' THEN total_tokens ELSE 0 END)  AS opus_tokens
  FROM commit_tokens
  GROUP BY git_sha
)
SELECT
  gc.git_sha,
  gc.commit_ts,
  cc.cluster_id,
  cc.commit_type,
  (cc.scope IS NOT NULL AND cc.scope <> '')                              AS has_scope,
  COALESCE(tok.tokens, 0) / 1e6                                          AS tokens_M,
  CASE WHEN COALESCE(tok.tokens,0) = 0 THEN 0
       ELSE COALESCE(tok.opus_tokens,0) * 1.0 / tok.tokens END           AS opus_pct,
  COALESCE(gm.pagerank, 0)                                               AS pagerank,
  COALESCE(gm.betweenness, 0)                                            AS betweenness,
  COALESCE(gm.degree, 0)                                                 AS degree
FROM git_commits gc
LEFT JOIN commit_classification cc USING (git_sha)
LEFT JOIN tok ON tok.git_sha = gc.git_sha
LEFT JOIN commit_graph_metrics gm USING (git_sha)
WHERE gc.commit_ts IS NOT NULL
""").fetchdf()

df["commit_ts"] = pd.to_datetime(df["commit_ts"], utc=True).dt.tz_convert("Pacific/Noumea")
df["hour"]       = df["commit_ts"].dt.hour
df["is_weekend"] = df["commit_ts"].dt.weekday.isin([5, 6]).astype(int)
df["is_feat"]    = (df["commit_type"] == "feat").astype(int)
df["is_fix"]     = (df["commit_type"] == "fix").astype(int)
df["has_scope"]  = df["has_scope"].astype(int)

# Continuous feature matrix for PC + Fisher's Z
FEATURES = [
    "tokens_M", "opus_pct", "pagerank", "betweenness", "degree",
    "is_feat", "is_fix", "has_scope", "hour", "is_weekend",
]
PRETTY = {
    "tokens_M":   "Tokens",
    "opus_pct":   "Opus %",
    "pagerank":   "PageRank",
    "betweenness":"Between-\nness",
    "degree":     "Degree",
    "is_feat":    "feat",
    "is_fix":     "fix",
    "has_scope":  "has\nscope",
    "hour":       "Hour",
    "is_weekend": "Weekend",
}

# Drop rows with any missing critical value
X = df[FEATURES].copy()
X = X.dropna()
print(f"PC input: {X.shape[0]} rows × {X.shape[1]} features")

# Standardise (PC + Fisher's Z prefers it; scale-free anyway, but helps)
X_std = (X - X.mean()) / X.std(ddof=0).replace(0, 1)
data = X_std.values

# ── 2. PC algorithm ────────────────────────────────────────────────────────
cg = pc(data, alpha=0.05, indep_test=fisherz, show_progress=False)

# Extract edges from cg.G (general graph object)
# Edge encoding: cg.G.graph[i,j] = -1 means i --> j
#                cg.G.graph[i,j] =  1 means i <-- j (so j --> i)
#                cg.G.graph[i,j] =  0 means no edge in this orientation
adj = cg.G.graph
nfeat = len(FEATURES)
edges_directed   = []  # (from, to)
edges_undirected = []  # (a, b) symmetric, unoriented residual

seen = set()
for i in range(nfeat):
    for j in range(nfeat):
        if i == j:
            continue
        if (i, j) in seen or (j, i) in seen:
            continue
        a, b = adj[i, j], adj[j, i]
        # The PC algorithm in causal-learn uses an "endpoint" encoding:
        # -1 = arrow tail at this node, 1 = arrow head
        if a == -1 and b == 1:
            edges_directed.append((i, j))
            seen.add((i, j))
        elif a == 1 and b == -1:
            edges_directed.append((j, i))
            seen.add((j, i))
        elif a == -1 and b == -1:
            # both endpoints tails → undirected edge
            edges_undirected.append((i, j))
            seen.add((i, j))

print(f"Directed edges discovered: {len(edges_directed)}")
print(f"Undirected edges (residual): {len(edges_undirected)}")
for s, t in edges_directed:
    print(f"  {FEATURES[s]:14s} -> {FEATURES[t]}")
for s, t in edges_undirected:
    print(f"  {FEATURES[s]:14s} -- {FEATURES[t]}  (orientation undetermined)")

# ── 3. Render the DAG ──────────────────────────────────────────────────────
G = nx.DiGraph()
for f in FEATURES:
    G.add_node(f, label=PRETTY[f])
for s, t in edges_directed:
    G.add_edge(FEATURES[s], FEATURES[t], directed=True)

# Manual layout: cluster related variables to make the DAG readable
positions = {
    "tokens_M":   (0.0,  1.0),
    "opus_pct":   (0.0,  0.0),
    "pagerank":   (-2.0, 0.8),
    "betweenness":(-2.0, 0.0),
    "degree":     (-2.0, -0.8),
    "is_feat":    (1.5,  1.2),
    "is_fix":     (1.5,  0.4),
    "has_scope":  (1.5, -0.4),
    "hour":       (0.0, -1.2),
    "is_weekend": (1.5, -1.2),
}

# Group colours by feature family
COLOURS = {
    "tokens_M":   "#7c3aed", "opus_pct":   "#7c3aed",     # AI usage
    "pagerank":   "#0f766e", "betweenness":"#0f766e", "degree": "#0f766e",  # graph
    "is_feat":    "#dc2626", "is_fix":     "#dc2626", "has_scope": "#dc2626",  # commit type
    "hour":       "#0891b2", "is_weekend": "#0891b2",     # temporal
}

fig, ax = plt.subplots(figsize=(10, 6))

# Nodes — bigger so labels fit
for f, (x, y) in positions.items():
    ax.scatter(x, y, s=4500, color=COLOURS[f], edgecolor="white",
               linewidth=1.8, zorder=2, alpha=0.92)
    ax.text(x, y, PRETTY[f], ha="center", va="center", fontsize=8.5,
            color="white", fontweight="bold", zorder=3, linespacing=1.0)

# Edges
for s, t in edges_directed:
    src, dst = FEATURES[s], FEATURES[t]
    x0, y0 = positions[src]
    x1, y1 = positions[dst]
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>", color="#1f2937",
                                lw=1.7, shrinkA=33, shrinkB=33,
                                connectionstyle="arc3,rad=0.10"),
                zorder=1)
for s, t in edges_undirected:
    src, dst = FEATURES[s], FEATURES[t]
    x0, y0 = positions[src]
    x1, y1 = positions[dst]
    ax.plot([x0, x1], [y0, y1], "--", color="#94a3b8", lw=1.4, zorder=1)

# Legend (family colours)
families = [
    ("Graph position",  "#0f766e"),
    ("Commit type",     "#dc2626"),
    ("Temporal",        "#0891b2"),
    ("AI usage (target)", "#7c3aed"),
]
for i, (name, c) in enumerate(families):
    ax.scatter([], [], s=120, color=c, label=name, edgecolor="white", linewidth=1)
ax.legend(loc="lower right", fontsize=8, frameon=True, framealpha=0.93)

ax.set_xlim(-3.0, 2.7)
ax.set_ylim(-2.0, 1.8)
ax.set_xticks([]); ax.set_yticks([])
for spine in ax.spines.values():
    spine.set_visible(False)
ax.set_title("Causal DAG (PC algorithm, Fisher's Z, α = 0.05) — "
             f"{len(edges_directed)} directed edges discovered",
             fontsize=11, fontweight="bold", pad=10)
ax.text(0.5, -0.07,
        "Solid arrow: causal direction estimated by PC. Dashed line: edge significant "
        "but orientation undetermined.",
        transform=ax.transAxes, ha="center", fontsize=8, style="italic", color="#475569")

plt.tight_layout()
OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT_PNG, dpi=160, bbox_inches="tight")
print(f"\nFigure → {OUT_PNG}")

# ── 4. Save JSON for the report ────────────────────────────────────────────
summary = {
    "n_samples": int(X.shape[0]),
    "n_features": int(X.shape[1]),
    "features": [{"key": f, "label": PRETTY[f], "family": (
        "graph" if f in {"pagerank","betweenness","degree"} else
        "type"  if f in {"is_feat","is_fix","has_scope"} else
        "time"  if f in {"hour","is_weekend"} else
        "usage"
    )} for f in FEATURES],
    "alpha": 0.05,
    "algorithm": "PC (Peter-Clark) with Fisher's Z",
    "edges_directed":   [{"from": FEATURES[s], "to": FEATURES[t],
                          "from_label": PRETTY[FEATURES[s]],
                          "to_label":   PRETTY[FEATURES[t]]}
                         for s, t in edges_directed],
    "edges_undirected": [{"a": FEATURES[s], "b": FEATURES[t]} for s, t in edges_undirected],
}

with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"Summary  → {OUT_JSON}")
print(json.dumps({k: v for k, v in summary.items() if k != "features"},
                 ensure_ascii=False, indent=2))
