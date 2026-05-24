"""Tests for the Aquavena scraper (offline, no real HTTP)."""

from aquavena_sdk.scraper import _parse_regimes

SAMPLE_HTML = """
<html><body>
  <div class="formule-home" style="background-image:url(https://www.aquavena.nc/sites/default/files/bien_etre.jpg)">
    <h3>Aqua Bien être / Family</h3>
    <p>Pour une alimentation équilibrée et diététique</p>
    <a href="/formules/aqua-bien-etre-family">EN SAVOIR PLUS</a>
  </div>
  <div class="formule-home" style="background-image:url(https://www.aquavena.nc/sites/default/files/chrono.jpg)">
    <h3>Aqua Chrono Diet</h3>
    <p>Pour une alimentation controlée, variée, équilibrée</p>
    <a href="/formules/aqua-chrono-diet">EN SAVOIR PLUS</a>
  </div>
  <div class="formule-home" style="background-image:url(https://www.aquavena.nc/sites/default/files/vege.jpg)">
    <h3>Aqua Végé</h3>
    <p>Pour une alimentation végétarienne variée et équilibrée</p>
    <a href="/formules/aqua-vege">EN SAVOIR PLUS</a>
  </div>
  <!-- duplicate card — must be deduplicated -->
  <div class="formule-home" style="background-image:url(https://www.aquavena.nc/sites/default/files/vege.jpg)">
    <h3>Aqua Végé</h3>
    <a href="/formules/aqua-vege">EN SAVOIR PLUS</a>
  </div>
  <!-- non-formule link outside a formule-home card — must be ignored -->
  <a href="/nos-menus/415">Voir menu</a>
</body></html>
"""


def test_parse_returns_regimes():
    regimes = _parse_regimes(SAMPLE_HTML)
    assert len(regimes) == 3


def test_regime_names():
    regimes = _parse_regimes(SAMPLE_HTML)
    names = [r.name for r in regimes]
    assert "Aqua Bien être / Family" in names
    assert "Aqua Chrono Diet" in names
    assert "Aqua Végé" in names


def test_regime_slugs():
    regimes = _parse_regimes(SAMPLE_HTML)
    slugs = {r.slug for r in regimes}
    assert slugs == {"aqua-bien-etre-family", "aqua-chrono-diet", "aqua-vege"}


def test_regime_description():
    regimes = _parse_regimes(SAMPLE_HTML)
    bien_etre = next(r for r in regimes if "Bien" in r.name)
    assert "équilibrée" in bien_etre.description


def test_regime_url_is_absolute():
    regimes = _parse_regimes(SAMPLE_HTML)
    for r in regimes:
        assert r.url.startswith("https://")


def test_image_url():
    regimes = _parse_regimes(SAMPLE_HTML)
    chrono = next(r for r in regimes if r.slug == "aqua-chrono-diet")
    assert chrono.image_url == "https://www.aquavena.nc/sites/default/files/chrono.jpg"


def test_image_url_empty_when_no_style():
    html = """
    <html><body>
      <div class="formule-home">
        <h3>Aqua Test</h3>
        <a href="/formules/aqua-test">EN SAVOIR PLUS</a>
      </div>
    </body></html>
    """
    regimes = _parse_regimes(html)
    assert regimes[0].image_url == ""


def test_deduplication():
    regimes = _parse_regimes(SAMPLE_HTML)
    slugs = [r.slug for r in regimes]
    assert len(slugs) == len(set(slugs)), "Duplicate slugs found"
