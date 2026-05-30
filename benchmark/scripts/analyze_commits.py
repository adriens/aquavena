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

    # ── Embeddings ────────────────────────────────────────────────────────
    print("Loading sentence-transformer model ...", file=sys.stderr)
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
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

    output = {
        "commits": [
            {
                "sha": c["sha"],
                "subject": c["subject"],
                "ts": c["ts"],
                "type": c["type"],
                "scope": c["scope"],
                "cluster": id_map[int(labels[i])],
                "x": float(coords[i, 0]),
                "y": float(coords[i, 1]),
            }
            for i, c in enumerate(commits)
        ],
        "clusters": clusters_info,
        "explained_variance": [float(v) for v in pca.explained_variance_ratio_],
        "n_clusters": n_clusters,
        "n_commits": len(commits),
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_dim": int(emb.shape[1]),
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
