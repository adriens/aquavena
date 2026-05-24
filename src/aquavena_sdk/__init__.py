"""Aquavena SDK — scraping utilities for https://www.aquavena.nc."""

__version__ = "0.1.0"

from .models import DayMenu, Dish, MealTime, Regime, RegimeMenu, RegimeTarif, TarifItem
from .scraper import AquavenaClient

__all__ = [
    "__version__",
    "AquavenaClient", "DayMenu", "Dish", "MealTime",
    "Regime", "RegimeMenu", "RegimeTarif", "TarifItem",
]
