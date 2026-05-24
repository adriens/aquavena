#!/usr/bin/env python3
"""Fetch Aquavena menus and write site/src/data/menus.json."""

import json
import sys
from datetime import datetime
from pathlib import Path

from aquavena_sdk import AquavenaClient
from aquavena_sdk.models import DayMenu

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "site" / "src" / "data" / "menus.json"


def _day(day: DayMenu) -> dict:
    return {
        "date": day.date,
        "label": day.label,
        "formule": day.formule,
        "plats": [{"meal_time": d.meal_time.value, "description": d.description} for d in day.plats],
        "supplements": day.supplements,
        "boissons": day.boissons,
    }


def main() -> None:
    print("Fetching data from aquavena.nc…", flush=True)
    regime_data = []
    with AquavenaClient() as client:
        regimes = client.list_regimes()
        for r in regimes:
            print(f"  {r.slug}", flush=True)
            try:
                m = client.get_menus(r.slug)
                menu = {"description": m.description, "days": [_day(d) for d in m.days]}
            except Exception as exc:
                print(f"  [warn] {exc}", file=sys.stderr)
                menu = {"description": "", "days": []}
            regime_data.append({
                "name": r.name,
                "slug": r.slug,
                "description": r.description,
                "image_url": r.image_url,
                "menu": menu,
            })

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": datetime.today().strftime("%Y-%m-%d"),
        "regimes": regime_data,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written to {OUT}", flush=True)


if __name__ == "__main__":
    main()
