# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "duckdb>=1.0",
#   "pandas>=2.0",
#   "numpy>=1.26",
#   "scikit-learn>=1.4",
#   "matplotlib>=3.8",
# ]
# ///
"""
Predict the token cost of a commit from its *structure and type alone* —
the "text-free CI triage" the report promises but never delivered.

The model never sees the commit message or the actual token count of related
work. It is given only:
  - graph position : PageRank, betweenness, degree (from the similarity graph)
  - commit type    : feat / fix / other one-hot, presence of a conv-commit scope
  - temporal       : hour of day (Pacific/Noumea), weekend flag
and must predict log(total tokens Claude spent on that commit).

Honest evaluation: a 70/30 train/test split, compared against a mean-predictor
baseline (Dummy) and an interpretable LinearRegression, with a Gradient
Boosting model as the main estimator. Metrics are reported on the held-out
test set only.

Inputs  : benchmark/data/benchmark.duckdb
Outputs : benchmark/data/token_prediction.json   (metrics + importances)
          benchmark/quarto/token_prediction.png  (predicted-vs-actual + importances)

Usage   : uv run --script benchmark/scripts/predict_token_cost.py
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "benchmark.duckdb"
OUT_JSON = ROOT / "data" / "token_prediction.json"
OUT_PNG = ROOT / "quarto" / "token_prediction.png"

RANDOM_STATE = 42
TEST_SIZE = 0.30

# ── 1. Pull one row per commit: target + structure/type/time features ───────
con = duckdb.connect(str(DB), read_only=True)
df = con.execute("""
WITH tok AS (
  SELECT git_sha, SUM(total_tokens) AS tokens
  FROM commit_tokens
  GROUP BY git_sha
)
SELECT
  gc.git_sha,
  gc.commit_ts,
  tok.tokens,
  cc.commit_type,
  (cc.scope IS NOT NULL AND cc.scope <> '') AS has_scope,
  gm.pagerank,
  gm.betweenness,
  gm.degree
FROM git_commits gc
JOIN tok                    ON tok.git_sha = gc.git_sha
JOIN commit_graph_metrics gm ON gm.git_sha = gc.git_sha
LEFT JOIN commit_classification cc ON cc.git_sha = gc.git_sha
WHERE gc.commit_ts IS NOT NULL AND tok.tokens > 0
""").fetchdf()
con.close()

# ── 2. Feature engineering (structure + type + time ONLY) ───────────────────
ts = pd.to_datetime(df["commit_ts"], utc=True).dt.tz_convert("Pacific/Noumea")
df["hour"]       = ts.dt.hour
df["is_weekend"] = ts.dt.weekday.isin([5, 6]).astype(int)
df["is_feat"]    = (df["commit_type"] == "feat").astype(int)
df["is_fix"]     = (df["commit_type"] == "fix").astype(int)
df["has_scope"]  = df["has_scope"].astype(int)

FEATURES = [
    "pagerank", "betweenness", "degree",   # graph structure
    "is_feat", "is_fix", "has_scope",      # commit type
    "hour", "is_weekend",                  # temporal
]
PRETTY = {
    "pagerank": "PageRank", "betweenness": "Betweenness", "degree": "Degree",
    "is_feat": "is_feat", "is_fix": "is_fix", "has_scope": "has_scope",
    "hour": "Hour", "is_weekend": "Weekend",
}

X = df[FEATURES].astype(float).values
y_tokens = df["tokens"].astype(float).values
y = np.log1p(y_tokens)            # heavy right-skew → model in log space

X_tr, X_te, y_tr, y_te, tok_tr, tok_te = train_test_split(
    X, y, y_tokens, test_size=TEST_SIZE, random_state=RANDOM_STATE
)

# ── 3. Models ───────────────────────────────────────────────────────────────
dummy = DummyRegressor(strategy="mean").fit(X_tr, y_tr)
linreg = LinearRegression().fit(X_tr, y_tr)
gbr = GradientBoostingRegressor(
    n_estimators=300, max_depth=2, learning_rate=0.05,
    subsample=0.8, random_state=RANDOM_STATE,
).fit(X_tr, y_tr)


def eval_model(model, name):
    pred_log = model.predict(X_te)
    pred_tok = np.expm1(pred_log)
    return {
        "model": name,
        "r2_log": float(r2_score(y_te, pred_log)),
        "mae_tokens": float(mean_absolute_error(tok_te, pred_tok)),
        "mae_tokens_millions": float(mean_absolute_error(tok_te, pred_tok) / 1e6),
    }


res_dummy = eval_model(dummy, "Mean baseline (Dummy)")
res_lin = eval_model(linreg, "Linear regression")
res_gbr = eval_model(gbr, "Gradient boosting")

# ── 4. Permutation importance (test set, the honest kind) ───────────────────
perm = permutation_importance(
    gbr, X_te, y_te, n_repeats=50, random_state=RANDOM_STATE
)
importances = sorted(
    [
        {"feature": PRETTY[f], "importance": float(m), "std": float(s)}
        for f, m, s in zip(FEATURES, perm.importances_mean, perm.importances_std)
    ],
    key=lambda d: d["importance"], reverse=True,
)

# ── 5. JSON output ──────────────────────────────────────────────────────────
out = {
    "n_commits": int(len(df)),
    "n_train": int(len(X_tr)),
    "n_test": int(len(X_te)),
    "test_size": TEST_SIZE,
    "random_state": RANDOM_STATE,
    "target": "log1p(total tokens per commit)",
    "features": [PRETTY[f] for f in FEATURES],
    "leakage_note": "No token-derived or message-text feature is used as input.",
    "median_tokens": float(np.median(y_tokens)),
    "mean_tokens": float(np.mean(y_tokens)),
    "results": [res_dummy, res_lin, res_gbr],
    "best_model": "Gradient boosting",
    "best_r2_log": res_gbr["r2_log"],
    "best_mae_tokens": res_gbr["mae_tokens"],
    "permutation_importance": importances,
}
OUT_JSON.write_text(json.dumps(out, indent=2))
print(json.dumps({k: v for k, v in out.items()
                  if k in ("n_commits", "n_train", "n_test", "results",
                           "best_r2_log", "best_mae_tokens")}, indent=2))

# ── 6. Figure: predicted-vs-actual (test) + permutation importance ─────────
pred_te_tok = np.expm1(gbr.predict(X_te))
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))

lim = [min(tok_te.min(), pred_te_tok.min()) / 1e6,
       max(tok_te.max(), pred_te_tok.max()) / 1e6]
ax1.scatter(tok_te / 1e6, pred_te_tok / 1e6, s=42, alpha=0.7,
            color="#0f766e", edgecolor="white", linewidth=0.6)
ax1.plot(lim, lim, "--", color="#94a3b8", linewidth=1.2, label="perfect")
ax1.set_xlabel("Actual tokens (millions)")
ax1.set_ylabel("Predicted tokens (millions)")
ax1.set_title(f"Held-out test set (n={len(X_te)})\n"
              f"Gradient boosting · R² (log) = {res_gbr['r2_log']:.2f}",
              fontsize=11)
ax1.legend(frameon=False, fontsize=9)
ax1.grid(alpha=0.25)

labels = [d["feature"] for d in importances][::-1]
vals = [d["importance"] for d in importances][::-1]
errs = [d["std"] for d in importances][::-1]
ax2.barh(labels, vals, xerr=errs, color="#5eead4", edgecolor="#0f766e")
ax2.set_xlabel("Permutation importance (drop in R²)")
ax2.set_title("What the model relies on", fontsize=11)
ax2.grid(axis="x", alpha=0.25)

fig.suptitle("Predicting commit token-cost from structure & type alone",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.95])
fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight")
print(f"\nFigure → {OUT_PNG}")
print(f"JSON   → {OUT_JSON}")
