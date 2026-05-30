#!/usr/bin/env python3
"""
Extract Claude Code token usage for this project from the local session
transcripts at ~/.claude/projects/-home-adriens-Github-aquavena/.

Output: benchmark/data/claude_usage.json
  {
    "total":            { "input": N, "output": N, "cache_read": N,
                          "cache_write": N, "total": N },
    "by_session":       [ { "session": "<uuid>", "started_at": ..., ... }, ... ],
    "by_day":           [ { "date": "YYYY-MM-DD", "input": N, ... }, ... ],
    "by_session_message": [ ... ]   # optional, kept compact
  }

Reads only the `message.usage` and `timestamp` fields — never the message bodies.

Usage:
    uv run python benchmark/scripts/extract_claude_usage.py
"""

from __future__ import annotations
import json
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT_PROJECT = Path("/home/adriens/.claude/projects/-home-adriens-Github-aquavena")
OUT = Path(__file__).resolve().parent.parent / "data" / "claude_usage.json"


def safe_int(x: Any) -> int:
    try:
        return int(x or 0)
    except Exception:
        return 0


def parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        # ISO 8601 with Z or +00:00
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def main() -> None:
    sessions: list[dict] = []
    usage_by_session_model: list[dict] = []
    by_day_raw: dict[str, dict[str, int]] = defaultdict(
        lambda: dict(input=0, output=0, cache_read=0, cache_write=0)
    )
    grand = dict(input=0, output=0, cache_read=0, cache_write=0)
    grand_user_messages = 0
    grand_assistant_messages = 0
    all_models: set[str] = set()

    for jsonl in sorted(ROOT_PROJECT.glob("*.jsonl")):
        session_id = jsonl.stem
        models: set[str] = set()
        # Per-model aggregation within this session
        per_model: dict[str, dict[str, int]] = defaultdict(
            lambda: dict(input=0, output=0, cache_read=0, cache_write=0, assistant_messages=0)
        )
        sess = dict(
            session=session_id,
            started_at=None,
            ended_at=None,
            user_messages=0,
            assistant_messages=0,
            input=0,
            output=0,
            cache_read=0,
            cache_write=0,
            total=0,
            models=[],
        )
        try:
            with jsonl.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    top_type = obj.get("type")
                    msg = obj.get("message") or {}
                    role = msg.get("role") if isinstance(msg, dict) else None
                    ts = obj.get("timestamp") or (msg.get("created_at") if isinstance(msg, dict) else None)
                    dt = parse_ts(ts)

                    # Count message types
                    if top_type == "user" or role == "user":
                        sess["user_messages"] += 1
                        grand_user_messages += 1
                    elif top_type == "assistant" or role == "assistant":
                        sess["assistant_messages"] += 1
                        grand_assistant_messages += 1
                        model = msg.get("model") if isinstance(msg, dict) else None
                        if model:
                            models.add(model)
                            all_models.add(model)
                            per_model[model]["assistant_messages"] += 1

                    # Update session time window from any timestamped event
                    if dt:
                        if sess["started_at"] is None or dt < parse_ts(sess["started_at"]):
                            sess["started_at"] = dt.isoformat()
                        if sess["ended_at"] is None or dt > parse_ts(sess["ended_at"]):
                            sess["ended_at"] = dt.isoformat()

                    usage = msg.get("usage") if isinstance(msg, dict) else None
                    if not usage:
                        continue
                    inp = safe_int(usage.get("input_tokens"))
                    out = safe_int(usage.get("output_tokens"))
                    crr = safe_int(usage.get("cache_read_input_tokens"))
                    cwr = safe_int(usage.get("cache_creation_input_tokens"))

                    sess["input"] += inp
                    sess["output"] += out
                    sess["cache_read"] += crr
                    sess["cache_write"] += cwr
                    grand["input"] += inp
                    grand["output"] += out
                    grand["cache_read"] += crr
                    grand["cache_write"] += cwr

                    # Per (session, model) breakdown for cost computation
                    model_for_usage = (msg.get("model") if isinstance(msg, dict) else None) or "unknown"
                    per_model[model_for_usage]["input"] += inp
                    per_model[model_for_usage]["output"] += out
                    per_model[model_for_usage]["cache_read"] += crr
                    per_model[model_for_usage]["cache_write"] += cwr

                    if dt:
                        d = dt.date().isoformat()
                        by_day_raw[d]["input"] += inp
                        by_day_raw[d]["output"] += out
                        by_day_raw[d]["cache_read"] += crr
                        by_day_raw[d]["cache_write"] += cwr
        except Exception as e:
            print(f"  ! {jsonl.name}: {e}", file=sys.stderr)
            continue

        sess["total"] = sess["input"] + sess["output"] + sess["cache_read"] + sess["cache_write"]
        sess["models"] = sorted(models)
        sessions.append(sess)

        # Emit per (session, model) rows
        for model_name, m in per_model.items():
            usage_by_session_model.append(dict(
                session=session_id,
                model=model_name,
                assistant_messages=m["assistant_messages"],
                input=m["input"],
                output=m["output"],
                cache_read=m["cache_read"],
                cache_write=m["cache_write"],
                total=m["input"] + m["output"] + m["cache_read"] + m["cache_write"],
            ))

    grand["total"] = sum(grand[k] for k in ("input", "output", "cache_read", "cache_write"))

    by_day = []
    for d, vals in sorted(by_day_raw.items()):
        total = sum(vals.values())
        by_day.append(dict(date=d, total=total, **vals))

    out = dict(
        total=grand,
        n_sessions=len(sessions),
        user_messages=grand_user_messages,
        assistant_messages=grand_assistant_messages,
        models=sorted(all_models),
        by_session=sessions,
        by_session_model=usage_by_session_model,
        by_day=by_day,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"Sessions          : {len(sessions)}")
    print(f"User messages     : {grand_user_messages:>10,}")
    print(f"Assistant messages: {grand_assistant_messages:>10,}")
    print(f"Models used       : {', '.join(sorted(all_models))}")
    print(f"Input tokens      : {grand['input']:>15,}")
    print(f"Output tokens     : {grand['output']:>15,}")
    print(f"Cache read        : {grand['cache_read']:>15,}")
    print(f"Cache write       : {grand['cache_write']:>15,}")
    print(f"TOTAL             : {grand['total']:>15,}")
    print(f"\nWritten {OUT}")


if __name__ == "__main__":
    main()
