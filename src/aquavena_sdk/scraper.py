"""Scraper for https://www.aquavena.nc."""

import re
from urllib.parse import unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from .models import Dish, DayMenu, MealTime, Regime, RegimeMenu, RegimeTarif, TarifItem

BASE_URL = "https://www.aquavena.nc"
MENUS_PATH = "/nos-menus"
FORMULES_PATH = "/formules/"
TARIFS_PATH = "/content/tarifs-conditions"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}

_MEAL_TIME_PREFIXES: list[tuple[str, MealTime]] = [
    ("GOURMET MIDI", MealTime.GOURMET_MIDI),
    ("GOURMET SOIR", MealTime.GOURMET_SOIR),
    ("MIDI", MealTime.MIDI),
    ("SOIR", MealTime.SOIR),
]


def _is_formule_link(href: str) -> bool:
    return "/formules/" in href and not href.endswith("/formules/")


def _slug_from_url(url: str) -> str:
    return unquote(urlparse(url).path.rstrip("/").split("/")[-1])


def _parse_meal_time(text: str) -> tuple[MealTime, str]:
    upper = text.upper()
    for prefix, meal_time in _MEAL_TIME_PREFIXES:
        if upper.startswith(prefix):
            # Remove the prefix and the separator (space, colon, space)
            rest = text[len(prefix):].lstrip(" :")
            return meal_time, rest
    return MealTime.UNKNOWN, text


def _parse_section(section_div: Tag) -> tuple[str, list[str]]:
    """Return (section_name, [item_texts]) from a day section block."""
    span = section_div.find("span", class_="type-plat-menu")
    name = span.get_text(strip=True) if span else ""
    items = [
        p.get_text(" ", strip=True)
        for p in section_div.find_all("p", class_="desc-plat")
    ]
    return name, items


def _parse_day_block(day_div: Tag) -> tuple[list[Dish], list[str], list[str], list[str]]:
    plats: list[Dish] = []
    supplements: list[str] = []
    boissons: list[str] = []
    boutique: list[str] = []

    for section in day_div.find_all("div", class_="text-center", recursive=False):
        # Each section has an h3 with type-plat-menu span
        name, items = _parse_section(section)
        key = name.lower()
        if key == "plat":
            for item in items:
                meal_time, desc = _parse_meal_time(item)
                plats.append(Dish(meal_time=meal_time, description=desc))
        elif key == "supplément":
            supplements.extend(items)
        elif key == "boisson":
            boissons.extend(items)
        elif key == "boutique":
            boutique.extend(items)

    return plats, supplements, boissons, boutique


def _parse_description(soup: BeautifulSoup) -> str:
    col = soup.find("div", class_="col-sm-8")
    if col:
        p = col.find("p")
        if p:
            return p.get_text(" ", strip=True)
    return ""


def _parse_regime_menu(html: str, slug: str) -> RegimeMenu:
    soup = BeautifulSoup(html, "html.parser")

    description = _parse_description(soup)

    # Day headers: ordered list of (date, label, formule)
    day_headers = [
        (
            d.get("data-date", ""),
            d.get_text(strip=True),
            d.get("data-formule", ""),
        )
        for d in soup.find_all("div", class_="slideto")
    ]

    # Menu content blocks: same order as day_headers
    menu_container = soup.find("div", id="slide-days-menu")
    if not menu_container:
        return RegimeMenu(slug=slug)

    day_blocks = [
        child
        for child in menu_container.children
        if isinstance(child, Tag) and child.name == "div"
    ]

    days: list[DayMenu] = []
    for (date, label, formule), block in zip(day_headers, day_blocks):
        # The actual sections are inside the first inner div
        inner = block.find("div")
        if not inner:
            continue
        plats, supplements, boissons, boutique = _parse_day_block(inner)
        days.append(
            DayMenu(
                date=date,
                label=label,
                formule=formule,
                plats=plats,
                supplements=supplements,
                boissons=boissons,
                boutique=boutique,
            )
        )

    return RegimeMenu(slug=slug, description=description, days=days)


_BG_IMAGE_RE = re.compile(r"background-image\s*:\s*url\(([^)]+)\)")


def _extract_bg_image(style: str) -> str:
    m = _BG_IMAGE_RE.search(style)
    return m.group(1).strip("\"'") if m else ""


def _parse_regimes(html: str) -> list[Regime]:
    soup = BeautifulSoup(html, "html.parser")
    seen_slugs: set[str] = set()
    regimes: list[Regime] = []

    for card in soup.find_all("div", class_="formule-home"):
        # Image from background-image style
        image_url = _extract_bg_image(card.get("style", ""))

        # Regime link
        a = card.find("a", href=lambda h: h and _is_formule_link(
            h if h.startswith("http") else urljoin(BASE_URL, h)
        ))
        if not a:
            continue

        href: str = a["href"]
        full_url = href if href.startswith("http") else urljoin(BASE_URL, href)
        slug = _slug_from_url(full_url)

        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Name: first heading in the card, else slug
        h_tag = card.find(["h2", "h3", "h4"])
        name = h_tag.get_text(strip=True) if h_tag else slug.replace("-", " ").title()

        # Description: first <p> in the card
        p_tag = card.find("p")
        description = p_tag.get_text(strip=True) if p_tag else ""

        regimes.append(
            Regime(
                name=name,
                description=description,
                url=full_url,
                slug=slug,
                image_url=image_url,
            )
        )

    return regimes


def _parse_price(text: str) -> int:
    return int(text.strip().replace(" ", "").replace("\xa0", "") or "0")


def _parse_tarifs(html: str) -> list[RegimeTarif]:
    soup = BeautifulSoup(html, "html.parser")
    tarifs: list[RegimeTarif] = []

    for table in soup.find_all("table"):
        table_id = table.get("id", "")
        thead = table.find("thead")
        if not thead:
            continue

        # Regime name is the first <th> of the first header row
        first_th = thead.find("th")
        regime_name = first_th.get_text(strip=True) if first_th else table_id

        items: list[TarifItem] = []
        for tr in table.find("tbody").find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 3:
                continue
            label    = cells[0].get_text(" ", strip=True)
            price_ht  = _parse_price(cells[1].get_text())
            price_ttc = _parse_price(cells[2].get_text())
            if label:
                items.append(TarifItem(label=label, price_ht=price_ht, price_ttc=price_ttc))

        tarifs.append(RegimeTarif(regime=regime_name, table_id=table_id, items=items))

    return tarifs


class AquavenaClient:
    """HTTP client for the Aquavena website."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 15.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={**DEFAULT_HEADERS, **(headers or {})},
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AquavenaClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def list_regimes(self, path: str = MENUS_PATH) -> list[Regime]:
        """Return all diet regimes listed on the /nos-menus page."""
        url = self._base_url + path
        response = self._client.get(url)
        response.raise_for_status()
        return _parse_regimes(response.text)

    def get_tarifs(self) -> list[RegimeTarif]:
        """Return all pricing tables from the tarifs page."""
        url = self._base_url + TARIFS_PATH
        response = self._client.get(url)
        response.raise_for_status()
        return _parse_tarifs(response.text)

    def get_menus(self, slug: str) -> RegimeMenu:
        """Return the structured weekly menus for the given regime slug."""
        url = self._base_url + FORMULES_PATH + slug
        response = self._client.get(url)
        response.raise_for_status()
        return _parse_regime_menu(response.text, slug)
