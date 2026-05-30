#!/usr/bin/env python3
"""
Extract per-release Lighthouse scores by joining git tags with ci_runs in DuckDB.

Output: data/score_history.json
  [{"tag": "v1.6.0", "sha": "534854c", "date": "2026-05-30", "score": 100, "pa11y_errors": 0}, ...]

Usage:
  uv run python benchmark/scripts/extract_score_history.py
  task score-history          (via Taskfile)
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT   = Path(__file__).resolve().parents[2]   # aquavena-sdk/
DB     = Path(__file__).resolve().parent.parent / "data" / "benchmark.duckdb"
OUT    = Path(__file__).resolve().parent.parent / "data" / "score_history.json"


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args],
                                   text=True).strip()


def build_tag_map() -> dict[str, dict]:
    """Return {short_sha: {tag, date}} for every annotated/lightweight tag."""
    raw = git("tag", "--sort=version:refname")
    tags = [t for t in raw.splitlines() if t.strip()]
    result: dict[str, dict] = {}
    for tag in tags:
        sha   = git("rev-list", "-n", "1", tag)[:7]
        date  = git("log", "-1", "--format=%as", sha)
        result[sha] = {"tag": tag, "date": date}
    return result


def query_duckdb(sql: str) -> list[dict]:
    """Run a DuckDB query and return rows as list-of-dicts."""
    try:
        import duckdb
    except ImportError:
        print("duckdb not installed — run: pip install duckdb", file=sys.stderr)
        sys.exit(1)

    if not DB.exists():
        print(f"DuckDB not found at {DB} — run 'task report:fresh' first.", file=sys.stderr)
        sys.exit(1)

    con = duckdb.connect(str(DB), read_only=True)
    rows = con.execute(sql).fetchall()
    cols = [d[0] for d in con.description]
    con.close()
    return [dict(zip(cols, row)) for row in rows]


def main() -> None:
    tag_map = build_tag_map()

    rows = query_duckdb("""
        SELECT git_sha, MIN(audit_date::VARCHAR) AS date,
               MAX(lh_score)     AS score,
               MIN(pa11y_errors) AS pa11y_errors
        FROM ci_runs
        WHERE git_sha IS NOT NULL
        GROUP BY git_sha
        ORDER BY MIN(audit_date)
    """)

    # Also pull git_sha from score_history for tags that have one stored
    sh_rows = query_duckdb("SELECT tag, git_sha FROM score_history WHERE git_sha IS NOT NULL")

    sh_sha_map = {r["tag"]: r["git_sha"] for r in sh_rows}

    history: list[dict] = []
    for row in rows:
        sha = (row["git_sha"] or "")[:7]
        meta = tag_map.get(sha, {})
        history.append({
            "tag":          meta.get("tag", sha),        # fall back to short SHA
            "sha":          sha,
            "date":         meta.get("date") or row["date"],
            "score":        int(row["score"] or 0),
            "pa11y_errors": int(row["pa11y_errors"] or 0),
        })

    # Tags that have no ci_runs entry yet get score = None (will be skipped in chart)
    tagged_shas = {v["sha"] for v in history}
    for sha, meta in tag_map.items():
        if sha not in tagged_shas:
            history.append({
                "tag":          meta["tag"],
                "sha":          sha,
                "date":         meta["date"],
                "score":        None,
                "pa11y_errors": None,
            })

    # Backfill sha from score_history table for tags missing it
    for entry in history:
        if not entry.get("sha") and entry["tag"] in sh_sha_map:
            entry["sha"] = sh_sha_map[entry["tag"]]

    # Sort by semver-aware tag order using git tag --sort output
    tag_order = {meta["tag"]: i for i, meta in enumerate(tag_map.values())}
    history.sort(key=lambda r: tag_order.get(r["tag"], 9999))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(history, indent=2))
    print(f"Written {len(history)} entries to {OUT}")


if __name__ == "__main__":
    main()
