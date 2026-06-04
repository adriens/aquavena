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


BIEN_ETRE_HTML = """
<html><body>
  <div class="text-center slideto" data-date="2026-06-08" data-formule="BE">
    <div class="slideto-inner"><span>Lundi 8 juin 2026</span></div>
  </div>
  <div id="slide-days-menu">
    <div class="text-center">
      <div>
        <div class="text-center">
          <h3><span class="type-plat-menu">Entrée</span></h3>
          <div class="text-center">
            <p class="desc-plat">Flan Saumon fumé, Chèvre &amp; Basilic</p>
            <p class="desc-plat">Pizza Margherita</p>
          </div>
        </div>
        <div class="text-center">
          <h3><span class="type-plat-menu">Plat</span></h3>
          <div class="text-center">
            <p class="desc-plat">Bœuf Bourguignon, Carottes, Spaghettis</p>
            <p class="desc-plat">GOURMET : Tajine de Souris d'Agneau aux Olives</p>
            <p class="desc-plat">Méditerranéen Midi : Magret de Canard au Chutney de figues</p>
            <p class="desc-plat">Méditerranéen Soir : Tajine de Boulettes de Lentilles</p>
            <p class="desc-plat">VEGE : Steak de Quinoa et Courgettes au Chèvre</p>
            <p class="desc-plat">FRESH : Salade de Quinoa Citronné, Pois chiches et Feta</p>
            <p class="desc-plat">Aqua'Kids (Portion Enfant) : Lasagnes au Poulet</p>
          </div>
        </div>
        <div class="text-center">
          <h3><span class="type-plat-menu">Dessert</span></h3>
          <div class="text-center">
            <p class="desc-plat">Crème Vanille Coulis caramel</p>
          </div>
        </div>
        <div class="text-center">
          <h3><span class="type-plat-menu">Dessert Sans Sucre / Sans Gluten</span></h3>
          <div class="text-center">
            <p class="desc-plat">Pannacotta au coulis de Framboises</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</body></html>
"""


def test_bien_etre_gourmet():
    day = _parse_regime_menu(BIEN_ETRE_HTML, "aqua-bien-être-family").days[0]
    gourmet = day.gourmet()
    assert len(gourmet) == 1
    assert gourmet[0].meal_time == MealTime.GOURMET
    assert "Tajine de Souris" in gourmet[0].description


def test_bien_etre_mediterraneen_midi():
    day = _parse_regime_menu(BIEN_ETRE_HTML, "aqua-bien-être-family").days[0]
    midi = day.midi()
    assert any("Magret" in d.description for d in midi)


def test_bien_etre_mediterraneen_soir():
    day = _parse_regime_menu(BIEN_ETRE_HTML, "aqua-bien-être-family").days[0]
    soir = day.soir()
    assert any("Boulettes de Lentilles" in d.description for d in soir)


def test_bien_etre_vege():
    day = _parse_regime_menu(BIEN_ETRE_HTML, "aqua-bien-être-family").days[0]
    vege = [d for d in day.plats if d.meal_time == MealTime.VEGE]
    assert len(vege) == 1
    assert "Quinoa" in vege[0].description


def test_bien_etre_fresh():
    day = _parse_regime_menu(BIEN_ETRE_HTML, "aqua-bien-être-family").days[0]
    fresh = [d for d in day.plats if d.meal_time == MealTime.FRESH]
    assert len(fresh) == 1
    assert "Salade" in fresh[0].description


def test_bien_etre_kids():
    day = _parse_regime_menu(BIEN_ETRE_HTML, "aqua-bien-être-family").days[0]
    kids = [d for d in day.plats if d.meal_time == MealTime.KIDS]
    assert len(kids) == 1
    assert "Lasagnes" in kids[0].description


def test_bien_etre_standard_plat_is_unknown():
    day = _parse_regime_menu(BIEN_ETRE_HTML, "aqua-bien-être-family").days[0]
    unknown = [d for d in day.plats if d.meal_time == MealTime.UNKNOWN]
    assert any("Bœuf" in d.description for d in unknown)


def test_bien_etre_entrees():
    day = _parse_regime_menu(BIEN_ETRE_HTML, "aqua-bien-être-family").days[0]
    assert len(day.entrees) == 2
    assert any("Saumon fumé" in e for e in day.entrees)
    assert any("Pizza" in e for e in day.entrees)


def test_bien_etre_desserts():
    day = _parse_regime_menu(BIEN_ETRE_HTML, "aqua-bien-être-family").days[0]
    assert len(day.desserts) == 2
    assert any("Crème Vanille" in d for d in day.desserts)
    assert any("Pannacotta" in d for d in day.desserts)
