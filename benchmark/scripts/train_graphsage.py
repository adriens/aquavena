"""
GraphSAGE on the commit similarity graph.

Task: predict each commit's semantic cluster (0..5) from its neighbours alone,
without using the BAAI/bge-m3 text embedding.  This is a cross-validation
of the K-Means clustering through a totally different inductive method.

Inputs:
  benchmark/data/commit_graph.gexf  (NetworkX GEXF; built by analyze_commits.py)

Outputs:
  benchmark/quarto/graphsage_results.png   confusion matrix + accuracy curve
  benchmark/data/graphsage_results.json    metrics for the Quarto report
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score,
    confusion_matrix, f1_score, classification_report,
)
from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv

# ── Paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "data" / "commit_graph.gexf"
RESULTS_JSON = ROOT / "data" / "graphsage_results.json"
RESULTS_PNG = ROOT / "quarto" / "graphsage_results.png"

# ── Load the commit graph ──────────────────────────────────────────────────
G = nx.read_gexf(GRAPH_PATH)
print(f"Loaded graph: {G.number_of_nodes()} nodes  {G.number_of_edges()} edges")

# Build a stable integer id ordering
node_ids = sorted(G.nodes())
id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

# ── Node features: structural only (NO BAAI embeddings) ────────────────────
# We deliberately exclude the cluster (target) and any feature derived from
# the text.  Structural features = PageRank, betweenness, degree, and
# commit_type one-hot.  These describe the node's POSITION IN THE GRAPH.
def safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

commit_types = sorted({(G.nodes[n].get("commit_type") or "other") for n in node_ids})
ct_to_idx = {ct: i for i, ct in enumerate(commit_types)}

features = []
labels = []
for n in node_ids:
    a = G.nodes[n]
    pr   = safe_float(a.get("pagerank"))
    bw   = safe_float(a.get("betweenness"))
    deg  = float(G.degree(n))
    ct_oh = np.zeros(len(commit_types), dtype=np.float32)
    ct_oh[ct_to_idx[a.get("commit_type") or "other"]] = 1.0
    features.append(np.concatenate([np.array([pr, bw, deg], dtype=np.float32), ct_oh]))
    labels.append(int(a.get("cluster")) if a.get("cluster") is not None else -1)

x = torch.tensor(np.stack(features), dtype=torch.float32)
y = torch.tensor(labels, dtype=torch.long)
print(f"Feature matrix: {tuple(x.shape)}  ·  classes: {sorted(set(labels))}")

# ── Edge index (undirected → bidirectional) ────────────────────────────────
src, dst = [], []
for u, v in G.edges():
    src.append(id_to_idx[u]); dst.append(id_to_idx[v])
    src.append(id_to_idx[v]); dst.append(id_to_idx[u])
edge_index = torch.tensor(np.stack([src, dst]), dtype=torch.long)

data = Data(x=x, y=y, edge_index=edge_index)

# ── Train/val/test split (stratified-ish, but simple random for 146 nodes) ─
n = data.num_nodes
torch.manual_seed(7)
perm = torch.randperm(n)
n_train = int(0.6 * n)
n_val   = int(0.2 * n)
train_mask = torch.zeros(n, dtype=torch.bool); train_mask[perm[:n_train]] = True
val_mask   = torch.zeros(n, dtype=torch.bool); val_mask[perm[n_train:n_train + n_val]] = True
test_mask  = torch.zeros(n, dtype=torch.bool); test_mask[perm[n_train + n_val:]] = True

data.train_mask = train_mask
data.val_mask   = val_mask
data.test_mask  = test_mask

num_classes = int(y.max().item()) + 1

# ── 2-layer GraphSAGE ──────────────────────────────────────────────────────
class GraphSAGE(torch.nn.Module):
    def __init__(self, in_dim, hidden_dim, out_dim):
        super().__init__()
        self.sage1 = SAGEConv(in_dim, hidden_dim)
        self.sage2 = SAGEConv(hidden_dim, out_dim)

    def forward(self, x, edge_index):
        h = self.sage1(x, edge_index)
        h = F.relu(h)
        h = F.dropout(h, p=0.4, training=self.training)
        return self.sage2(h, edge_index)


model = GraphSAGE(in_dim=x.shape[1], hidden_dim=32, out_dim=num_classes)
opt = torch.optim.Adam(model.parameters(), lr=1e-2, weight_decay=5e-4)

# Class weights for imbalance robustness
weights = torch.tensor(
    [1.0 / max(1, (y == c).sum().item()) for c in range(num_classes)],
    dtype=torch.float32,
)
weights = weights / weights.sum() * num_classes  # normalise so mean=1

# ── Training loop ──────────────────────────────────────────────────────────
EPOCHS = 200
history = {"epoch": [], "train_loss": [], "train_acc": [], "val_acc": []}

for epoch in range(1, EPOCHS + 1):
    model.train()
    opt.zero_grad()
    out = model(data.x, data.edge_index)
    loss = F.cross_entropy(out[train_mask], y[train_mask], weight=weights)
    loss.backward()
    opt.step()

    model.eval()
    with torch.no_grad():
        pred = model(data.x, data.edge_index).argmax(dim=1)
        train_acc = float((pred[train_mask] == y[train_mask]).float().mean())
        val_acc   = float((pred[val_mask]   == y[val_mask]).float().mean())
    history["epoch"].append(epoch)
    history["train_loss"].append(float(loss.item()))
    history["train_acc"].append(train_acc)
    history["val_acc"].append(val_acc)

# ── Final test-set metrics ─────────────────────────────────────────────────
model.eval()
with torch.no_grad():
    pred = model(data.x, data.edge_index).argmax(dim=1)

test_pred = pred[test_mask].cpu().numpy()
test_true = y[test_mask].cpu().numpy()
test_acc = accuracy_score(test_true, test_pred)
bal_acc  = balanced_accuracy_score(test_true, test_pred)
f1_macro = f1_score(test_true, test_pred, average="macro")
cm = confusion_matrix(test_true, test_pred, labels=list(range(num_classes)))

# Baseline: majority class accuracy
maj_cls = int(np.bincount(y.numpy()).argmax())
baseline_acc = float((y[test_mask] == maj_cls).float().mean())

print(f"Test accuracy:     {test_acc:.3f}")
print(f"Balanced accuracy: {bal_acc:.3f}")
print(f"Macro F1:          {f1_macro:.3f}")
print(f"Majority baseline: {baseline_acc:.3f}")

# ── Save figure: confusion + learning curve ────────────────────────────────
CLUSTER_LABELS = {
    0: "Site features\n& About",
    1: "Style &\ndark mode",
    2: "Benchmark\n& ML report",
    3: "Project identity\n& links",
    4: "WCAG fixes",
    5: "Links &\nmerges",
}
labels_pretty = [CLUSTER_LABELS.get(i, f"C{i}") for i in range(num_classes)]

fig, axes = plt.subplots(1, 2, figsize=(11, 4.0), gridspec_kw={"width_ratios": [1.2, 1]})

# Learning curve
ax = axes[0]
ax.plot(history["epoch"], history["train_acc"], label="Train accuracy",
        color="#0f766e", linewidth=1.4)
ax.plot(history["epoch"], history["val_acc"],   label="Validation accuracy",
        color="#7c3aed", linewidth=1.4)
ax.axhline(baseline_acc, color="#9ca3af", linestyle="--", linewidth=0.8,
           label=f"Majority baseline ({baseline_acc:.2f})")
ax.set_xlabel("Epoch")
ax.set_ylabel("Accuracy")
ax.set_title("GraphSAGE training curve — 2 layers, hidden=32, CPU only")
ax.set_ylim(0, 1)
ax.legend(loc="lower right", fontsize=8)
ax.grid(alpha=0.25)

# Confusion matrix
ax = axes[1]
row_sums = cm.sum(axis=1, keepdims=True)
cm_norm = np.where(row_sums > 0, cm / np.maximum(row_sums, 1), 0)
im = ax.imshow(cm_norm, cmap="Greens", vmin=0, vmax=1, aspect="auto")
for i in range(num_classes):
    for j in range(num_classes):
        v = cm[i, j]
        if row_sums[i, 0] > 0:
            pct = cm_norm[i, j] * 100
            txt = f"{int(v)}\n{pct:.0f}%"
        else:
            txt = "—"
        ax.text(j, i, txt, ha="center", va="center", fontsize=7,
                color="white" if cm_norm[i, j] > 0.55 else "#1f2937")
ax.set_xticks(range(num_classes))
ax.set_yticks(range(num_classes))
ax.set_xticklabels(labels_pretty, fontsize=7)
ax.set_yticklabels(labels_pretty, fontsize=7)
ax.set_xlabel("Predicted cluster")
ax.set_ylabel("True cluster")
ax.set_title(f"Test confusion · acc={test_acc:.2f} · F1={f1_macro:.2f}")
plt.colorbar(im, ax=ax, fraction=0.045, pad=0.04, label="row share")

plt.tight_layout()
RESULTS_PNG.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(RESULTS_PNG, dpi=160, bbox_inches="tight")
print(f"\nFigure → {RESULTS_PNG}")

# ── Save metrics for the report ────────────────────────────────────────────
report = classification_report(
    test_true, test_pred,
    labels=list(range(num_classes)),
    target_names=[CLUSTER_LABELS.get(i, f"C{i}").replace("\n", " ") for i in range(num_classes)],
    output_dict=True, zero_division=0,
)

# Compute "best confused pair" off-diagonal
off = cm.copy().astype(float)
np.fill_diagonal(off, 0.0)
i_off, j_off = np.unravel_index(np.argmax(off), off.shape)
best_confused = {
    "true": CLUSTER_LABELS.get(int(i_off), f"C{int(i_off)}").replace("\n", " "),
    "predicted": CLUSTER_LABELS.get(int(j_off), f"C{int(j_off)}").replace("\n", " "),
    "count": int(off[i_off, j_off]),
}

# Self-loops (correct predictions) per class as the share of that class
diag_pct = []
for c in range(num_classes):
    if row_sums[c, 0] > 0:
        diag_pct.append({
            "cluster": CLUSTER_LABELS.get(c, f"C{c}").replace("\n", " "),
            "recall": float(cm[c, c] / row_sums[c, 0]),
            "support": int(row_sums[c, 0]),
        })

summary = {
    "n_nodes": int(G.number_of_nodes()),
    "n_edges": int(G.number_of_edges()),
    "n_features": int(x.shape[1]),
    "feature_names": [
        "pagerank", "betweenness", "degree",
        *[f"commit_type::{ct}" for ct in commit_types],
    ],
    "n_classes": int(num_classes),
    "model": "GraphSAGE-2layer-h32",
    "epochs": EPOCHS,
    "train_acc": float(history["train_acc"][-1]),
    "val_acc":   float(history["val_acc"][-1]),
    "test_acc":  float(test_acc),
    "test_balanced_acc": float(bal_acc),
    "test_macro_f1":     float(f1_macro),
    "majority_baseline": float(baseline_acc),
    "lift_over_baseline": float(test_acc - baseline_acc),
    "best_confused_pair": best_confused,
    "per_class_recall": diag_pct,
    "split_sizes": {
        "train": int(train_mask.sum()),
        "val":   int(val_mask.sum()),
        "test":  int(test_mask.sum()),
    },
}

with open(RESULTS_JSON, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f"Summary  → {RESULTS_JSON}")
print(json.dumps(summary, ensure_ascii=False, indent=2))
