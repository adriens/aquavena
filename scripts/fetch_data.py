#!/usr/bin/env python3
"""Fetch Aquavena menus and write site/src/data/menus.json."""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from aquavena_sdk import AquavenaClient
from aquavena_sdk.models import DayMenu

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "site" / "src" / "data" / "menus.json"

MAX_RETRIES = 3
RETRY_DELAY = 15  # seconds


def _day(day: DayMenu) -> dict:
    return {
        "date": day.date,
        "label": day.label,
        "formule": day.formule,
        "plats": [{"meal_time": d.meal_time.value, "description": d.description} for d in day.plats],
        "supplements": day.supplements,
        "boissons": day.boissons,
    }


def _fetch() -> list:
    regime_data = []
    with AquavenaClient(timeout=30.0) as client:
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
    return regime_data


def main() -> None:
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"Fetching data from aquavena.nc… (tentative {attempt}/{MAX_RETRIES})", flush=True)
        try:
            regime_data = _fetch()
            break
        except Exception as exc:
            print(f"[erreur] {exc}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                print(f"Nouvelle tentative dans {RETRY_DELAY}s…", flush=True)
                time.sleep(RETRY_DELAY)
            else:
                if OUT.exists():
                    print(f"Toutes les tentatives ont échoué — conservation de {OUT}", file=sys.stderr)
                    sys.exit(0)
                print("Toutes les tentatives ont échoué et aucun fichier existant.", file=sys.stderr)
                sys.exit(1)

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
