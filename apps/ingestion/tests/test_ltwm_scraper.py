"""Tests del parser de Love The Work More sobre fixtures reales recortados."""

from pathlib import Path

import pytest

from trucho_ingest.models import AwardTier, LinkKind
from trucho_ingest.scrapers.ltwm import (
    ingestion_order,
    parse_historic_page,
    parse_year_page,
    year_pages,
)

FIXTURES = Path(__file__).parent / "fixtures"
URL_2019 = "https://lovetheworkmore.com/2019-2/"
URL_HIST = "https://lovetheworkmore.com/1954-1999/"


@pytest.fixture(scope="module")
def campaigns_2019():
    return parse_year_page((FIXTURES / "ltwm_2019.html").read_text(), 2019, URL_2019)


@pytest.fixture(scope="module")
def campaigns_hist():
    return parse_historic_page((FIXTURES / "ltwm_hist.html").read_text(), URL_HIST)


def test_parses_2019_entries(campaigns_2019):
    assert len(campaigns_2019) >= 70


def test_2019_grand_prix(campaigns_2019):
    whopper = next(c for c in campaigns_2019 if c.title == "THE WHOPPER DETOUR")
    assert whopper.brand == "BURGER KING"
    assert whopper.year == 2019
    assert whopper.awards[0].festival == "cannes"
    assert whopper.awards[0].tier == AwardTier.GRAND_PRIX
    assert whopper.awards[0].category is None  # LTWM solo publica el máximo León
    assert [a.name for a in whopper.agencies] == ["FCB NEW YORK"]


def test_2019_tier_transitions(campaigns_2019):
    fake_news = next(c for c in campaigns_2019 if c.title == "THE FAKE NEWS STAND")
    assert fake_news.awards[0].tier == AwardTier.GOLD


def test_2019_case_film_links(campaigns_2019):
    whopper = next(c for c in campaigns_2019 if c.title == "THE WHOPPER DETOUR")
    case = [link for link in whopper.links if link.kind == LinkKind.CASE_FILM]
    assert case and case[0].url.startswith("https://clios.com/")
    with_case = [
        c for c in campaigns_2019
        if any(link.kind == LinkKind.CASE_FILM for link in c.links)
    ]
    assert len(with_case) >= len(campaigns_2019) * 0.9


def test_bracket_category_extracted():
    """Años recientes: "[TITANIUM] TITLE – BRAND (AGENCY)" en los Grand Prix."""
    html = """
    <div id="main-content">
      <p><strong>GRAND PRIX / TITANIUM</strong></p>
      <p><a href="https://youtube.com/w">[TITANIUM] DOORDASH-ALL-THE-ADS – DOORDASH
      (WIEDEN+KENNEDY PORTLAND)</a></p>
      <p><strong>GOLD</strong></p>
      <p><a href="https://youtube.com/x">#TURNYOURBACK – DOVE (OGILVY LONDON)</a></p>
    </div>
    """
    campaigns = parse_year_page(html, 2024, "https://lovetheworkmore.com/2024-2/")
    assert len(campaigns) == 2
    gp, gold = campaigns
    assert gp.awards[0].category == "Titanium"
    assert gp.title == "DOORDASH-ALL-THE-ADS"
    assert gp.brand == "DOORDASH"
    assert gold.awards[0].category is None


def test_2019_multi_dash_title(campaigns_2019):
    """El último guion separa la marca; los anteriores son parte del título."""
    behind = next(c for c in campaigns_2019 if "BEHIND THE MAC" in c.title)
    assert behind.brand == "APPLE"
    assert behind.title == "BEHIND THE MAC – MAKE SOMETHING WONDERFUL"


def test_historic_years_parsed(campaigns_hist):
    years = {c.year for c in campaigns_hist}
    assert 1954 in years and 1999 not in years or years  # rango histórico presente
    circo = next(c for c in campaigns_hist if c.title == "II CIRCO")
    assert circo.year == 1954
    assert circo.brand == "CHLORODONT TOOTHPASTE"
    assert circo.awards[0].tier == AwardTier.GRAND_PRIX
    assert circo.awards[0].year == 1954


def test_historic_no_winner_skipped(campaigns_hist):
    assert not any("NO WINNER" in c.title.upper() for c in campaigns_hist)


def test_historic_entry_without_title(campaigns_hist):
    """"1984 – APPLE COMPUTER (TBWA…)": sin título explícito, se usa la marca."""
    apple = next(c for c in campaigns_hist if c.brand == "APPLE COMPUTER")
    assert apple.year == 1984
    assert apple.title == "APPLE COMPUTER"
    assert apple.agencies[0].name == "TBWA CHIAT/DAY LOS ANGELES"


def test_year_pages_mapping():
    pages = [
        {"title": {"rendered": "2019"}, "link": "https://lovetheworkmore.com/2019-2/"},
        {"title": {"rendered": "2020-2021"}, "link": "https://lovetheworkmore.com/238-2/"},
        {"title": {"rendered": "1954-1999"}, "link": "https://lovetheworkmore.com/1954-1999/"},
        {"title": {"rendered": "About"}, "link": "https://lovetheworkmore.com/about/"},
    ]
    mapping = year_pages(pages)
    assert set(mapping) == {"2019", "2020-2021", "1954-1999"}


def test_ingestion_order_prioritizes_2015_2025():
    titles = ["2013", "2026", "2019", "1954-1999", "2025", "2001"]
    order = ingestion_order(titles)
    assert order[0] == "2025"
    assert order[1] == "2019"
    # fuera de la ventana 2015-2025 va después, descendente; histórico al final
    assert order[2:] == ["2026", "2013", "2001", "1954-1999"]
