"""Tests for regime menu parsing (offline)."""

from aquavena_sdk.models import MealTime
from aquavena_sdk.scraper import _parse_regime_menu

SAMPLE_MENU_HTML = """
<html><body>
  <!-- Day headers -->
  <div class="text-center slideto" data-date="2026-05-18" data-formule="CD">
    <div class="slideto-inner"><span>Lundi 18 mai 2026</span></div>
  </div>
  <div class="text-center slideto" data-date="2026-05-19" data-formule="CD">
    <div class="slideto-inner"><span>Mardi 19 mai 2026</span></div>
  </div>

  <!-- Menu content -->
  <div id="slide-days-menu">

    <div class="text-center">
      <div>
        <div class="text-center">
          <h3><span class="type-plat-menu">Plat</span></h3>
          <div class="text-center">
            <p class="desc-plat">Midi : Cassoulet aux saucisses fumées</p>
            <p class="desc-plat">Midi : Poulet au Pesto Rosso, Polenta</p>
            <p class="desc-plat">Soir : Rougail de Seiches, Achards de légumes</p>
            <p class="desc-plat">GOURMET MIDI : Magret de Canard caramélisé</p>
          </div>
        </div>
        <div class="text-center">
          <h3><span class="type-plat-menu">Supplément</span></h3>
          <div class="text-center">
            <p class="desc-plat">Butternut rôtie</p>
            <p class="desc-plat">Riz blanc</p>
          </div>
        </div>
        <div class="text-center">
          <h3><span class="type-plat-menu">Boisson</span></h3>
          <div class="text-center">
            <p class="desc-plat">Perrier Forever Fraise 25cl</p>
          </div>
        </div>
      </div>
    </div>

    <div class="text-center">
      <div>
        <div class="text-center">
          <h3><span class="type-plat-menu">Plat</span></h3>
          <div class="text-center">
            <p class="desc-plat">Midi : Boulettes de Veau</p>
            <p class="desc-plat">Soir : Thon mi-cuit</p>
            <p class="desc-plat">GOURMET SOIR : Saumon Poêlé</p>
          </div>
        </div>
        <div class="text-center">
          <h3><span class="type-plat-menu">Supplément</span></h3>
          <div class="text-center">
            <p class="desc-plat">Haricots verts</p>
          </div>
        </div>
        <div class="text-center">
          <h3><span class="type-plat-menu">Boisson</span></h3>
          <div class="text-center">
            <p class="desc-plat">Eau Minérale 50cl</p>
          </div>
        </div>
      </div>
    </div>

  </div>
</body></html>
"""


def test_parse_returns_regime_menu():
    menu = _parse_regime_menu(SAMPLE_MENU_HTML, "aqua-chrono-diet")
    assert menu.slug == "aqua-chrono-diet"
    assert len(menu.days) == 2


def test_day_dates():
    menu = _parse_regime_menu(SAMPLE_MENU_HTML, "aqua-chrono-diet")
    assert menu.days[0].date == "2026-05-18"
    assert menu.days[1].date == "2026-05-19"


def test_day_labels():
    menu = _parse_regime_menu(SAMPLE_MENU_HTML, "aqua-chrono-diet")
    assert "Lundi" in menu.days[0].label
    assert "Mardi" in menu.days[1].label


def test_formule_code():
    menu = _parse_regime_menu(SAMPLE_MENU_HTML, "aqua-chrono-diet")
    assert menu.days[0].formule == "CD"


def test_plats_midi():
    day = _parse_regime_menu(SAMPLE_MENU_HTML, "aqua-chrono-diet").days[0]
    midi = day.midi()
    assert len(midi) == 2
    assert any("Cassoulet" in d.description for d in midi)
    assert any("Poulet" in d.description for d in midi)


def test_plats_soir():
    day = _parse_regime_menu(SAMPLE_MENU_HTML, "aqua-chrono-diet").days[0]
    soir = day.soir()
    assert len(soir) == 1
    assert "Rougail" in soir[0].description


def test_gourmet_midi():
    day = _parse_regime_menu(SAMPLE_MENU_HTML, "aqua-chrono-diet").days[0]
    gourmet = day.gourmet()
    assert len(gourmet) == 1
    assert gourmet[0].meal_time == MealTime.GOURMET_MIDI
    assert "Magret" in gourmet[0].description


def test_gourmet_soir():
    day = _parse_regime_menu(SAMPLE_MENU_HTML, "aqua-chrono-diet").days[1]
    gourmet = day.gourmet()
    assert len(gourmet) == 1
    assert gourmet[0].meal_time == MealTime.GOURMET_SOIR
    assert "Saumon" in gourmet[0].description


def test_supplements():
    day = _parse_regime_menu(SAMPLE_MENU_HTML, "aqua-chrono-diet").days[0]
    assert "Butternut rôtie" in day.supplements
    assert "Riz blanc" in day.supplements


def test_boissons():
    day = _parse_regime_menu(SAMPLE_MENU_HTML, "aqua-chrono-diet").days[0]
    assert len(day.boissons) == 1
    assert "Perrier" in day.boissons[0]


def test_empty_container():
    html = "<html><body><p>Pas de menus</p></body></html>"
    menu = _parse_regime_menu(html, "test-slug")
    assert menu.days == []
