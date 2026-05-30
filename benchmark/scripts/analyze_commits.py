#!/usr/bin/env python3
"""
Semantic analysis of git commit messages: embeddings + clustering + 2D
projection. Uses sentence-transformers/all-MiniLM-L6-v2 (small 80 MB model).

Output: benchmark/data/commit_semantics.json
  {
    "commits": [ { "sha", "subject", "ts", "type", "cluster", "x", "y" }, ... ],
    "clusters": [ { "id", "size", "terms": [...], "exemplar": "..." }, ... ],
    "explained_variance": [v1, v2]
  }

# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "sentence-transformers>=3.0,<4",
#   "scikit-learn>=1.4",
#   "numpy>=1.26",
#   "networkx>=3.2",
#   "matplotlib>=3.8",
#   "fa2-modified>=0.3.10",
#   "datashader>=0.16",
#   "pandas>=2.0",
#   "scikit-image>=0.22",
#   "dask>=2024.1",
# ]
# ///

Usage:
    uv run --script benchmark/scripts/analyze_commits.py
"""

from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parents[1] / "data" / "commit_semantics.json"

CONV_RE = re.compile(r"^(\w+)(?:\(([^)]*)\))?:")


def get_classification(subject: str) -> tuple[str, str | None]:
    """Return (commit_type, scope) from a conventional-commit subject."""
    m = CONV_RE.match(subject)
    if m:
        return m.group(1).lower(), (m.group(2) or "").lower() or None
    return "other", None


def main() -> None:
    log = subprocess.check_output(
        ["git", "-C", str(ROOT), "log", "--all", "--pretty=format:%h|%s|%aI"],
        text=True,
    )
    commits: list[dict] = []
    for line in log.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        sha, subject, ts = parts
        commit_type, scope = get_classification(subject)
        commits.append({"sha": sha, "subject": subject, "ts": ts,
                         "type": commit_type, "scope": scope})
    print(f"Loaded {len(commits)} commits", file=sys.stderr)

    subjects = [c["subject"] for c in commits]

    # ── Embeddings (multilingual model — handles mixed FR/EN commit msgs) ─
    MODEL_NAME = "BAAI/bge-m3"
    print(f"Loading {MODEL_NAME} (multilingual, 1024-dim) ...", file=sys.stderr)
    model = SentenceTransformer(MODEL_NAME)
    print("Encoding ...", file=sys.stderr)
    emb = model.encode(subjects, show_progress_bar=False, normalize_embeddings=True)
    print(f"Embeddings shape: {emb.shape}", file=sys.stderr)

    # ── Cluster ───────────────────────────────────────────────────────────
    n_clusters = min(6, max(2, len(commits) // 12))
    print(f"KMeans (k={n_clusters}) ...", file=sys.stderr)
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(emb)

    # ── 2D projection (PCA) ───────────────────────────────────────────────
    print("PCA → 2D ...", file=sys.stderr)
    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(emb)

    # ── TF-IDF for cluster labels ─────────────────────────────────────────
    vectorizer = TfidfVectorizer(
        max_features=200,
        stop_words=None,    # commit messages are short, keep all words
        ngram_range=(1, 2),
        lowercase=True,
        token_pattern=r"\b[a-zA-Z][a-zA-Z\-]+\b",   # words ≥ 2 chars, no digits
    )
    tfidf = vectorizer.fit_transform(subjects)
    feature_names = vectorizer.get_feature_names_out()

    clusters_info = []
    for k in range(n_clusters):
        mask = labels == k
        if not mask.any():
            continue
        avg_tfidf = np.asarray(tfidf[mask].mean(axis=0)).ravel()
        top_idx = avg_tfidf.argsort()[-6:][::-1]
        terms = [feature_names[i] for i in top_idx if avg_tfidf[i] > 0][:5]
        # Exemplar: closest commit message to the cluster centroid
        cluster_emb = emb[mask]
        centroid = cluster_emb.mean(axis=0, keepdims=True)
        cluster_subjects = [s for s, m in zip(subjects, mask) if m]
        dists = ((cluster_emb - centroid) ** 2).sum(axis=1)
        exemplar = cluster_subjects[int(dists.argmin())]
        clusters_info.append({
            "id": int(k),
            "size": int(mask.sum()),
            "terms": terms,
            "exemplar": exemplar,
        })

    # Sort clusters by size, descending
    clusters_info.sort(key=lambda c: -c["size"])
    # Re-map cluster ids 0..N-1 by size order
    id_map = {c["id"]: rank for rank, c in enumerate(clusters_info)}
    for c in clusters_info:
        c["id"] = id_map[c["id"]]

    # ── Graph data science: cosine-similarity graph + centrality ─────────
    import networkx as nx
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    SIM_THRESHOLD = 0.55   # cosine similarity threshold for edge inclusion
    print(f"Building similarity graph (threshold={SIM_THRESHOLD}) ...",
          file=sys.stderr)
    sim = emb @ emb.T  # all embeddings normalised → dot product = cosine
    np.fill_diagonal(sim, 0.0)
    G = nx.Graph()
    for i in range(len(commits)):
        G.add_node(i)
    for i in range(len(commits)):
        for j in range(i + 1, len(commits)):
            if sim[i, j] >= SIM_THRESHOLD:
                G.add_edge(i, j, weight=float(sim[i, j]))

    pr   = nx.pagerank(G, weight="weight")
    bc   = nx.betweenness_centrality(G, weight=None)
    deg  = dict(G.degree())

    # Annotate each commit with its centrality metrics
    for i, c in enumerate(commits):
        c["pagerank"]    = float(pr.get(i, 0.0))
        c["betweenness"] = float(bc.get(i, 0.0))
        c["degree"]      = int(deg.get(i, 0))
        c["cluster"]     = id_map[int(labels[i])]

    # Anchor commits = top PageRank per cluster (cluster-representative)
    anchors_per_cluster = {}
    for c in commits:
        k = c["cluster"]
        if k not in anchors_per_cluster or c["pagerank"] > anchors_per_cluster[k]["pagerank"]:
            anchors_per_cluster[k] = c

    # Bridge commits = top betweenness globally (link distinct themes)
    bridges = sorted(commits, key=lambda c: -c["betweenness"])[:5]

    # ── Render the network as a PNG (ForceAtlas2 layout, Gephi-native) ───
    print("Rendering graph PNG (ForceAtlas2 layout) ...", file=sys.stderr)
    fig, ax = plt.subplots(figsize=(9, 7.0), dpi=160)
    palette = {0: "#0f766e", 1: "#dc2626", 2: "#0891b2",
               3: "#7c3aed", 4: "#f59e0b", 5: "#059669", 6: "#db2777"}

    # ForceAtlas2 — same algorithm Gephi uses by default
    try:
        from fa2_modified import ForceAtlas2
        forceatlas2 = ForceAtlas2(
            outboundAttractionDistribution=True,   # dissuade hubs
            edgeWeightInfluence=1.0,
            jitterTolerance=1.0,
            barnesHutOptimize=True,
            barnesHutTheta=1.2,
            scalingRatio=2.0,
            strongGravityMode=False,
            gravity=1.0,
            verbose=False,
        )
        pos = forceatlas2.forceatlas2_networkx_layout(G, pos=None, iterations=600)
        print("  using fa2-modified (Gephi ForceAtlas2 port)", file=sys.stderr)
    except Exception as e:
        print(f"  fa2-modified unavailable ({e}); falling back to spring_layout",
              file=sys.stderr)
        pos = nx.spring_layout(G, k=0.45, iterations=400, seed=42, weight="weight")

    # Normalise PageRank to [0, 1] then power-scale → ~25× size ratio
    pr_arr = np.array([commits[i]["pagerank"] for i in G.nodes()])
    pr_lo, pr_hi = pr_arr.min(), pr_arr.max()
    if pr_hi > pr_lo:
        pr_norm = (pr_arr - pr_lo) / (pr_hi - pr_lo)
    else:
        pr_norm = np.ones_like(pr_arr) * 0.5
    # Power = 0.7 softens the contrast a touch but keeps it dramatic
    node_sizes = 70 + 1800 * (pr_norm ** 0.7)
    node_colors = [palette.get(commits[i]["cluster"], "#94a3b8") for i in G.nodes()]
    # Edge widths proportional to cosine-similarity weight (above threshold).
    # `(weight − threshold) / (1 − threshold)` rescales [threshold, 1] → [0, 1].
    edge_list = list(G.edges(data=True))
    edge_widths = [
        0.20 + 2.20 * max(0.0,
                          (d.get("weight", SIM_THRESHOLD) - SIM_THRESHOLD)
                          / max(1e-6, 1.0 - SIM_THRESHOLD))
        for _, _, d in edge_list
    ]
    edge_alphas = [
        0.10 + 0.55 * max(0.0,
                          (d.get("weight", SIM_THRESHOLD) - SIM_THRESHOLD)
                          / max(1e-6, 1.0 - SIM_THRESHOLD))
        for _, _, d in edge_list
    ]
    nx.draw_networkx_edges(
        G, pos, ax=ax,
        edgelist=[(u, v) for u, v, _ in edge_list],
        width=edge_widths,
        alpha=edge_alphas,
        edge_color="#374151",
    )
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                            node_size=node_sizes, edgecolors="white",
                            linewidths=0.7, alpha=0.92)
    # Label only the anchors + bridges to avoid clutter
    label_nodes = {}
    for c in anchors_per_cluster.values():
        idx = next(i for i, cc in enumerate(commits) if cc["sha"] == c["sha"])
        label_nodes[idx] = c["subject"][:40] + ("…" if len(c["subject"]) > 40 else "")
    for c in bridges:
        idx = next(i for i, cc in enumerate(commits) if cc["sha"] == c["sha"])
        if idx not in label_nodes:
            label_nodes[idx] = "[bridge] " + c["subject"][:36] + ("…" if len(c["subject"]) > 36 else "")
    for i, lbl in label_nodes.items():
        ax.annotate(lbl, xy=pos[i], xytext=(8, 6), textcoords="offset points",
                     fontsize=6.4, color="#0f172a",
                     bbox=dict(boxstyle="round,pad=0.18", fc="white",
                                ec="#cbd5e1", lw=0.4, alpha=0.92))
    ax.set_title("Commit-similarity graph — force-directed layout · node size = PageRank",
                  fontsize=10, fontweight="bold")
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values(): spine.set_visible(False)
    fig.tight_layout()
    graph_png = Path(__file__).resolve().parents[1] / "quarto" / "commit_graph.png"
    fig.savefig(graph_png, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {graph_png}", file=sys.stderr)

    # ── Artistic cover-page render (galactic constellation) ──────────────
    print("Rendering artistic cover-page PNG ...", file=sys.stderr)
    try:
        from fa2_modified import ForceAtlas2
        fa2_art = ForceAtlas2(
            outboundAttractionDistribution=True,
            linLogMode=True,            # tighter cluster separation
            edgeWeightInfluence=1.0,
            jitterTolerance=0.4,
            barnesHutOptimize=True,
            barnesHutTheta=1.2,
            scalingRatio=8.0,           # big spacing → prevents overlap
            strongGravityMode=True,
            gravity=12.0,               # stronger pull (was 4.0)
            verbose=False,
        )
        pos_art = fa2_art.forceatlas2_networkx_layout(G, pos=None, iterations=1400)
        # Post-process: nudge any pair of nodes that's still too close
        # (cheap O(n^2) push — fine for n=82)
        coords_arr = np.array([pos_art[i] for i in G.nodes()], dtype=float)
        min_dist = 0.025 * (coords_arr.max(0) - coords_arr.min(0)).max()
        for _ in range(40):
            moved = False
            for i in range(len(coords_arr)):
                for j in range(i + 1, len(coords_arr)):
                    d = coords_arr[j] - coords_arr[i]
                    dist = np.linalg.norm(d)
                    if 0 < dist < min_dist:
                        push = (min_dist - dist) / 2 * (d / max(dist, 1e-6))
                        coords_arr[i] -= push
                        coords_arr[j] += push
                        moved = True
            if not moved:
                break
        nodes_list = list(G.nodes())
        pos_art = {nodes_list[k]: tuple(coords_arr[k]) for k in range(len(nodes_list))}
    except Exception:
        pos_art = nx.spring_layout(G, k=0.45, iterations=600, seed=7, weight="weight")

    BG = "#0a0e1a"
    luminescent = {0: "#5eead4", 1: "#f87171", 2: "#67e8f9",
                    3: "#c4b5fd", 4: "#fbbf24", 5: "#86efac", 6: "#f0abfc"}

    fig_art, ax_art = plt.subplots(figsize=(9, 9), dpi=300, facecolor=BG)
    ax_art.set_facecolor(BG)

    # Edge bundling — datashader hammer-bundle for "fiber" look
    bundled_ok = False
    try:
        import pandas as pd
        from datashader.bundling import hammer_bundle
        print("Bundling edges (datashader hammer_bundle) ...", file=sys.stderr)
        nodes_list = list(G.nodes())
        node_idx = {n: i for i, n in enumerate(nodes_list)}
        nodes_df = pd.DataFrame({
            "x":    [pos_art[n][0] for n in nodes_list],
            "y":    [pos_art[n][1] for n in nodes_list],
            "name": list(range(len(nodes_list))),
        })
        # Split edges by weight tier — bundle each tier separately so the
        # strong intra-cluster bonds stand out brighter than the weak bridges
        weight_buckets = [
            {"label": "strong",  "lo": 0.75, "alpha": 0.78, "lw": 1.30, "colour": "#a5f3fc"},
            {"label": "medium",  "lo": 0.65, "alpha": 0.50, "lw": 0.85, "colour": "#7dd3fc"},
            {"label": "weak",    "lo": SIM_THRESHOLD, "alpha": 0.28, "lw": 0.50, "colour": "#38bdf8"},
        ]
        for tier in weight_buckets:
            sub = [(u, v, d) for u, v, d in G.edges(data=True)
                   if d.get("weight", 0) >= tier["lo"]
                   and (tier["lo"] == SIM_THRESHOLD or d.get("weight", 0) >= tier["lo"])
                   and d.get("weight", 0) < (1.01 if tier["lo"] >= 0.75 else
                                              0.75 if tier["lo"] >= 0.65 else 0.65)]
            if not sub:
                continue
            sub_edges = pd.DataFrame({
                "source": [node_idx[u] for u, v, _ in sub],
                "target": [node_idx[v] for u, v, _ in sub],
            })
            try:
                bundled = hammer_bundle(
                    nodes_df, sub_edges,
                    initial_bandwidth=0.07,
                    decay=0.7,
                    accuracy=500,
                    advect_iterations=30,
                )
                ax_art.plot(bundled.x.values, bundled.y.values,
                            color=tier["colour"], alpha=tier["alpha"],
                            linewidth=tier["lw"], zorder=1, solid_capstyle="round")
            except Exception as e:
                print(f"  bundling {tier['label']} failed: {e}", file=sys.stderr)
        bundled_ok = True
        print("  done", file=sys.stderr)
    except Exception as e:
        print(f"  datashader unavailable ({e}); using straight edges",
              file=sys.stderr)

    if not bundled_ok:
        # Fallback: straight luminous filaments
        for u, v, d in G.edges(data=True):
            w = float(d.get("weight", SIM_THRESHOLD))
            strength = max(0.0, (w - SIM_THRESHOLD) / max(1e-6, 1.0 - SIM_THRESHOLD))
            edge_alpha = 0.18 + 0.65 * strength
            edge_width = 0.35 + 1.65 * strength
            x_pos = [pos_art[u][0], pos_art[v][0]]
            y_pos = [pos_art[u][1], pos_art[v][1]]
            ax_art.plot(x_pos, y_pos, color="#7dd3fc",
                        alpha=edge_alpha, linewidth=edge_width, zorder=1)

    # Percentile-based sizing with power expansion for dramatic top-heaviness:
    # the few "anchor" commits become bright stars; most others stay modest.
    pr_arr_full = np.array([commits[i]["pagerank"] for i in G.nodes()])
    ranks       = np.argsort(np.argsort(pr_arr_full))          # 0 .. N-1 (low → high)
    percentiles = ranks / max(1, len(pr_arr_full) - 1)         # → [0, 1]
    # Power 1.6 EXPANDS the high end: top-10% dominate, bottom-60% stay small
    node_size_factor = percentiles ** 1.6

    # Nodes with multi-layer glow — dramatic size contrast (~80× area ratio)
    for k, i in enumerate(G.nodes()):
        c        = commits[i]
        color    = luminescent.get(c["cluster"], "#cbd5e1")
        f        = float(node_size_factor[k])
        core_s   = 18 + 2200 * f
        mid_s    = core_s * 3.4
        halo_s   = core_s * 11.0
        x, y     = pos_art[i]
        # Outer halo
        ax_art.scatter(x, y, s=halo_s, color=color,
                        alpha=0.10, edgecolors="none", zorder=2)
        # Mid glow
        ax_art.scatter(x, y, s=mid_s, color=color,
                        alpha=0.24, edgecolors="none", zorder=3)
        # Bright core
        ax_art.scatter(x, y, s=core_s, color=color,
                        alpha=0.98, edgecolors="white",
                        linewidths=0.7, zorder=4)

    ax_art.set_xticks([]); ax_art.set_yticks([])
    for spine in ax_art.spines.values(): spine.set_visible(False)
    ax_art.set_aspect("equal", adjustable="datalim")
    fig_art.tight_layout(pad=0)
    cover_png = Path(__file__).resolve().parents[1] / "quarto" / "commit_graph_cover.png"
    fig_art.savefig(cover_png, dpi=300, bbox_inches="tight",
                     facecolor=BG, edgecolor="none", pad_inches=0.20)
    plt.close(fig_art)
    print(f"  → {cover_png}", file=sys.stderr)

    # ── Export to GEXF for Gephi ─────────────────────────────────────────
    print("Writing Gephi-ready GEXF ...", file=sys.stderr)
    # GEXF rejects None — sanitise everything to strings/numbers
    cluster_hex = {0: "#0f766e", 1: "#dc2626", 2: "#0891b2",
                    3: "#7c3aed", 4: "#f59e0b", 5: "#059669"}
    Gx = nx.Graph()
    for i in G.nodes():
        c = commits[i]
        col = cluster_hex.get(c["cluster"], "#94a3b8")
        # Convert hex → RGB triplet for Gephi's viz attribute
        r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
        Gx.add_node(
            c["sha"],
            label       = c["subject"][:80],
            sha         = c["sha"],
            subject     = c["subject"],
            timestamp   = c["ts"] or "",
            commit_type = c["type"] or "",
            scope       = c["scope"] or "",
            cluster     = int(c["cluster"]),
            pagerank    = float(c["pagerank"]),
            betweenness = float(c["betweenness"]),
            degree      = int(c["degree"]),
            viz         = {"color": {"r": r, "g": g, "b": b},
                            "size": 5 + 25 * float(pr_norm[i])}
        )
    for u, v, data in G.edges(data=True):
        Gx.add_edge(commits[u]["sha"], commits[v]["sha"],
                     weight=float(data.get("weight", 1.0)))
    gexf_path = Path(__file__).resolve().parents[1] / "data" / "commit_graph.gexf"
    nx.write_gexf(Gx, gexf_path)
    print(f"  → {gexf_path}", file=sys.stderr)

    print()
    print("=== Anchor commit per cluster (highest PageRank) ===")
    for k in sorted(anchors_per_cluster):
        a = anchors_per_cluster[k]
        print(f"  C{k}  PR={a['pagerank']:.4f}  {a['subject'][:70]}")
    print("\n=== Bridges (highest betweenness — link distinct themes) ===")
    for c in bridges:
        print(f"  BC={c['betweenness']:.4f}  C{c['cluster']}  {c['subject'][:65]}")

    output = {
        "commits": [
            {
                "sha":         c["sha"],
                "subject":     c["subject"],
                "ts":          c["ts"],
                "type":        c["type"],
                "scope":       c["scope"],
                "cluster":     c["cluster"],
                "x":           float(coords[i, 0]),
                "y":           float(coords[i, 1]),
                "pagerank":    c["pagerank"],
                "betweenness": c["betweenness"],
                "degree":      c["degree"],
            }
            for i, c in enumerate(commits)
        ],
        "clusters": clusters_info,
        "explained_variance": [float(v) for v in pca.explained_variance_ratio_],
        "n_clusters": n_clusters,
        "n_commits": len(commits),
        "model": MODEL_NAME,
        "embedding_dim": int(emb.shape[1]),
        "graph": {
            "similarity_threshold": SIM_THRESHOLD,
            "edges":  int(G.number_of_edges()),
            "anchors": [
                {"cluster": k, "sha": a["sha"], "subject": a["subject"],
                 "pagerank": a["pagerank"]}
                for k, a in sorted(anchors_per_cluster.items())
            ],
            "bridges": [
                {"sha": b["sha"], "subject": b["subject"],
                 "cluster": b["cluster"], "betweenness": b["betweenness"]}
                for b in bridges
            ],
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print()
    print(f"=== {len(commits)} commits clustered into {n_clusters} groups ===")
    for c in clusters_info:
        print(f"  Cluster {c['id']} ({c['size']:3d} commits) — terms: {', '.join(c['terms'])}")
        print(f"     exemplar: {c['exemplar'][:90]}")
    print(f"\nExplained variance (PCA 2D): {sum(output['explained_variance'])*100:.1f}%")
    print(f"\nWritten {OUT}")


if __name__ == "__main__":
    main()
