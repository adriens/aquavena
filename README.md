# aquavena

[![Tests](https://github.com/adriens/aquavena/actions/workflows/tests.yml/badge.svg)](https://github.com/adriens/aquavena/actions/workflows/tests.yml)
[![PyPI version](https://badge.fury.io/py/aquavena-sdk.svg)](https://pypi.org/project/aquavena-sdk/)

[![Site GitHub Pages](https://img.shields.io/badge/Site-GitHub%20Pages-teal)](https://adriens.github.io/aquavena/)
[![AIM Score](https://img.shields.io/badge/AIM%20Score-10%2F10-brightgreen)](https://adriens.github.io/aquavena/about/)
[![WCAG AA](https://img.shields.io/badge/WCAG-AA-green)](https://adriens.github.io/aquavena/about/)
[![Malvoyants](https://img.shields.io/badge/Optimis%C3%A9-Malvoyants-blueviolet)](https://adriens.github.io/aquavena/about/)

[![RSS](https://img.shields.io/badge/RSS-Feed-orange)](https://adriens.github.io/aquavena/feed.xml)
[![iCal](https://img.shields.io/badge/iCal-Calendrier-blue)](https://adriens.github.io/aquavena/cal.ics)

[![Hugging Face Space](https://img.shields.io/badge/🤗%20Hugging%20Face-MCP%20Space-FFD21E)](https://huggingface.co/spaces/rastadidi/aquavena)
[![Claude Skill](https://img.shields.io/badge/Claude-Skill-8A2BE2)](https://adriens.github.io/claude-commands/skills/aquavena/)

SDK Python + CLI pour scraper les menus et tarifs d'[Aquavena](https://www.aquavena.nc) — service de livraison de repas diététiques en Nouvelle-Calédonie.

## Installation

```bash
pip install aquavena-sdk
# ou avec uv
uv add aquavena-sdk
```

## CLI

```bash
# Lister tous les régimes disponibles
aquavena list

# Menus d'un régime (toutes les semaines publiées)
aquavena menus aqua-méditerranéen
aquavena menus aqua-chrono-diet

# Grille tarifaire complète (tous régimes)
aquavena tarifs
```

## SDK

```python
from aquavena_sdk import AquavenaClient

with AquavenaClient() as client:

    # Lister les régimes
    regimes = client.list_regimes()
    for r in regimes:
        print(r.name, r.slug, r.image_url)

    # Menus d'un régime
    menu = client.get_menus("aqua-méditerranéen")
    print(menu.description)
    for day in menu.days:
        print(day.date, day.label)
        for dish in day.midi():
            print("  midi :", dish.description)
        for dish in day.soir():
            print("  soir :", dish.description)

    # Tarifs
    tarifs = client.get_tarifs()
    for rt in tarifs:
        print(rt.regime)
        for item in rt.items:
            print(f"  {item.label}: {item.price_ttc} XPF TTC")
```

### Filtrer les jours à venir

```python
from datetime import date
from aquavena_sdk import AquavenaClient

with AquavenaClient() as client:
    menu = client.get_menus("aqua-chrono-diet")

upcoming = [d for d in menu.days if date.fromisoformat(d.date) >= date.today()]
```

## Modèles

| Classe | Champs principaux |
|---|---|
| `Regime` | `name`, `slug`, `description`, `url`, `image_url` |
| `RegimeMenu` | `slug`, `description`, `days: list[DayMenu]` |
| `DayMenu` | `date`, `label`, `formule`, `plats`, `supplements`, `boissons` |
| `Dish` | `meal_time: MealTime`, `description` |
| `MealTime` | `MIDI`, `SOIR`, `GOURMET_MIDI`, `GOURMET_SOIR` |
| `RegimeTarif` | `regime`, `table_id`, `items: list[TarifItem]` |
| `TarifItem` | `label`, `price_ht`, `price_ttc` (XPF) |

## Régimes disponibles

| Slug | Régime |
|---|---|
| `aqua-bien-être-family` | Aqua Bien Être / Family |
| `aqua-chrono-diet` | Aqua Chrono Diet |
| `aqua-chrono-végé` | Aqua Chrono Végé |
| `aqua-méditerranéen` | Aqua Méditerranéen |
| `aqua-gourmand` | Aqua Gourmand |
| `aqua-végé` | Aqua Végé |
| `aqua-low-carb` | Aqua Low Carb |
| `aquasportif` | Aqua'Sportif |

## Développement

```bash
git clone https://github.com/adriens/aquavena
cd aquavena
uv sync
uv run pytest
uv run aquavena list
```

## Licence

MIT
