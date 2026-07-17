"""Tests del parser de El Ojo sobre un fixture real (Film 2025, recortado)."""

from pathlib import Path

import pytest

from trucho_ingest.models import AwardTier, LinkKind
from trucho_ingest.scrapers.elojo import discover_category_pages, parse_category_page

FIXTURE = Path(__file__).parent / "fixtures" / "elojo_film_2025.html"
SOURCE_URL = (
    "https://www.elojodeiberoamerica.com/premio/finalistas-y-ganadores-2025/el-ojo-film-2025/"
)


@pytest.fixture(scope="module")
def campaigns():
    return parse_category_page(FIXTURE.read_text(), 2025, SOURCE_URL)


def test_parses_a_reasonable_number_of_entries(campaigns):
    assert len(campaigns) >= 25


def test_grand_prix_entry(campaigns):
    gp = [
        c
        for c in campaigns
        if any(a.tier == AwardTier.GRAND_PRIX for a in c.awards)
    ]
    assert len(gp) >= 1
    sweeter = gp[0]
    assert sweeter.title == "Sweeter than the sweetest"
    assert sweeter.brand == "Axe/Lynx"
    assert sweeter.country == "ES"
    assert sweeter.year == 2025
    assert [a.name for a in sweeter.agencies] == ["LOLA MullenLowe"]
    assert sweeter.agencies[0].country == "ES"


def test_award_metadata(campaigns):
    match = next(c for c in campaigns if c.title == "Juntos en todas")
    award = match.awards[0]
    assert award.festival == "el-ojo"
    assert award.year == 2025
    assert award.tier == AwardTier.SILVER
    assert "FL1" in (award.category or "")
    assert match.brand == "Coca-Cola"
    assert match.country == "AR"


def test_case_film_links_extracted(campaigns):
    with_case = [
        c
        for c in campaigns
        if any(link.kind == LinkKind.CASE_FILM for link in c.links)
    ]
    # la gran mayoría de las piezas linkea a LatinSpots
    assert len(with_case) >= len(campaigns) * 0.7
    for c in campaigns:
        assert any(link.kind == LinkKind.FESTIVAL_PAGE for link in c.links)


def test_multiple_agencies_split(campaigns):
    match = next(c for c in campaigns if c.title == "Built for tough")
    names = [a.name for a in match.agencies]
    assert "Wieden+Kennedy São Paulo" in names
    assert "Wieden+Kennedy Buenos Aires" in names
    assert match.country == "BR"


def test_chilean_entry(campaigns):
    match = next(c for c in campaigns if c.title == "Don’t stop motion")
    assert match.country == "CL"
    assert match.awards[0].tier == AwardTier.BRONZE
    assert [a.name for a in match.agencies] == ["VML Chile"]


def test_raw_text_carries_context(campaigns):
    for c in campaigns:
        assert "El Ojo de Iberoamérica 2025" in c.raw_text
        assert c.source_site == "elojo"


def test_tier_inherited_by_following_entries(campaigns):
    """Entradas sin header repetido heredan el tier vigente (dos platas seguidas)."""
    abogados = next(c for c in campaigns if c.title == "Abogados")
    medicos = next(c for c in campaigns if c.title == "Médicos")
    assert abogados.awards[0].tier == AwardTier.SILVER
    assert medicos.awards[0].tier == AwardTier.SILVER


def test_discover_category_pages():
    hub = """
    <html><body>
      <a href="/premio/finalistas-y-ganadores-2025/el-ojo-film-2025/">Film</a>
      <a href="https://www.elojodeiberoamerica.com/premio/finalistas-y-ganadores-2025/el-ojo-digital-social-2025/">Digital</a>
      <a href="/premio/finalistas-y-ganadores-2024/">Otro año</a>
      <a href="/noticias/algo/">Noticia</a>
    </body></html>
    """
    urls = discover_category_pages(hub, 2025)
    assert urls == [
        "https://www.elojodeiberoamerica.com/premio/finalistas-y-ganadores-2025/el-ojo-film-2025/",
        "https://www.elojodeiberoamerica.com/premio/finalistas-y-ganadores-2025/el-ojo-digital-social-2025/",
    ]
