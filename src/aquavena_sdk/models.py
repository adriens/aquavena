from dataclasses import dataclass, field
from enum import Enum


@dataclass
class Regime:
    name: str
    description: str
    url: str
    slug: str = ""
    image_url: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.slug and self.url:
            self.slug = self.url.rstrip("/").split("/")[-1]

    def __repr__(self) -> str:
        return f"Regime(name={self.name!r}, slug={self.slug!r})"


class MealTime(str, Enum):
    MIDI = "midi"
    SOIR = "soir"
    GOURMET_MIDI = "gourmet_midi"
    GOURMET_SOIR = "gourmet_soir"
    UNKNOWN = "unknown"


@dataclass
class Dish:
    meal_time: MealTime
    description: str

    def __repr__(self) -> str:
        return f"Dish({self.meal_time.value}: {self.description!r})"


@dataclass
class DayMenu:
    date: str          # ISO format: "2026-05-18"
    label: str         # "Lundi 18 mai 2026"
    formule: str       # e.g. "CD"
    plats: list[Dish] = field(default_factory=list)
    supplements: list[str] = field(default_factory=list)
    boissons: list[str] = field(default_factory=list)
    boutique: list[str] = field(default_factory=list)

    def midi(self) -> list[Dish]:
        return [d for d in self.plats if d.meal_time == MealTime.MIDI]

    def soir(self) -> list[Dish]:
        return [d for d in self.plats if d.meal_time == MealTime.SOIR]

    def gourmet(self) -> list[Dish]:
        return [d for d in self.plats if d.meal_time in (MealTime.GOURMET_MIDI, MealTime.GOURMET_SOIR)]


@dataclass
class TarifItem:
    label: str
    price_ht: int   # XPF
    price_ttc: int  # XPF


@dataclass
class RegimeTarif:
    regime: str
    table_id: str
    items: list[TarifItem] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"RegimeTarif(regime={self.regime!r}, items={len(self.items)})"


@dataclass
class RegimeMenu:
    slug: str
    description: str = ""
    days: list[DayMenu] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"RegimeMenu(slug={self.slug!r}, days={len(self.days)})"
