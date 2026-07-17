"""Tests de dedupe cross-fuente contra Postgres real (pgvector).

Se corren solo si TRUCHO_TEST_DATABASE_URL está definida (CI levanta un
servicio pgvector/pgvector:pg16; local: apuntar a una DB de prueba, NUNCA a
la de producción — las tablas se truncan entre tests).
"""

import os

import pytest

from trucho_ingest.models import (
    Award,
    AwardTier,
    CampaignLink,
    LinkKind,
    RawCampaign,
    SourceConfidence,
)

TEST_DB = os.environ.get("TRUCHO_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="TRUCHO_TEST_DATABASE_URL no definida"
)


@pytest.fixture()
def conn(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    from trucho_ingest.db import repo

    with repo.connect() as c:
        repo.migrate(c)
        c.execute("truncate campaigns, agencies, tags cascade")
        yield c
        c.rollback()


def _elojo_juntos() -> RawCampaign:
    return RawCampaign(
        title="Juntos en todas",
        brand="Coca-Cola",
        year=2025,
        country="AR",
        awards=[Award(festival="el-ojo", year=2025,
                      category="Film — Alimentos y bebidas", tier=AwardTier.SILVER)],
        links=[CampaignLink(kind=LinkKind.CASE_FILM, url="https://latinspots.com/x")],
        raw_text="El Ojo 2025...",
        source_site="elojo",
        source_url="https://www.elojodeiberoamerica.com/x",
    )


def _ltwm_juntos() -> RawCampaign:
    # la misma pieza, como la publica LTWM: en mayúsculas y sin categoría
    return RawCampaign(
        title="JUNTOS EN TODAS",
        brand="COCA-COLA",
        year=2025,
        awards=[Award(festival="cannes", year=2025, category=None,
                      tier=AwardTier.GOLD)],
        links=[CampaignLink(kind=LinkKind.CASE_FILM, url="https://youtube.com/y")],
        raw_text="Cannes Lions 2025...",
        source_site="ltwm",
        source_url="https://lovetheworkmore.com/2025-2/",
    )


def _archive_litany() -> RawCampaign:
    return RawCampaign(
        title="Litany",
        brand="The Independent",
        year=1999,
        country="GB",
        awards=[Award(festival="cannes", year=1999, category="Film",
                      tier=AwardTier.GRAND_PRIX)],
        links=[CampaignLink(kind=LinkKind.FESTIVAL_PAGE,
                            url="https://archive.org/details/cannes-lions-advertising-film-winners")],
        raw_text="Archive dataset...",
        source_site="archive-org-cla",
        source_url="https://archive.org/details/cannes-lions-advertising-film-winners",
        confidence=SourceConfidence.LOW,
    )


def _ltwm_litany() -> RawCampaign:
    return RawCampaign(
        title="LITANY",
        brand="THE INDEPENDENT",
        year=1999,
        awards=[Award(festival="cannes", year=1999, category=None,
                      tier=AwardTier.GRAND_PRIX)],
        links=[CampaignLink(kind=LinkKind.CASE_FILM, url="https://youtube.com/z")],
        raw_text="LTWM 1954-1999...",
        source_site="ltwm",
        source_url="https://lovetheworkmore.com/1954-1999/",
    )


def _count(conn, sql, *args) -> int:
    return conn.execute(sql, args).fetchone()["n"]


def test_ltwm_and_archive_merge_into_one_campaign(conn):
    """Colisión LTWM + Archive (1954-2000): una campaña, premios fusionados."""
    from trucho_ingest.db import repo

    id_a = repo.upsert_raw_campaign(conn, _archive_litany())
    id_b = repo.upsert_raw_campaign(conn, _ltwm_litany())
    assert id_a == id_b

    assert _count(conn, "select count(*) as n from campaigns") == 1
    # el grand_prix de LTWM (sin categoría) NO duplica el de Archive (con categoría)
    assert _count(conn, "select count(*) as n from awards where campaign_id = %s", id_a) == 1
    category = conn.execute(
        "select category from awards where campaign_id = %s", (id_a,)
    ).fetchone()["category"]
    assert category == "Film"
    # las dos fuentes quedan trazadas, cada una con su confianza
    sources = conn.execute(
        "select source_site, confidence from sources where campaign_id = %s order by 1",
        (id_a,),
    ).fetchall()
    assert [(s["source_site"], s["confidence"]) for s in sources] == [
        ("archive-org-cla", "low"),
        ("ltwm", "normal"),
    ]
    # los links de ambas fuentes se suman
    n_links = _count(conn, "select count(*) as n from campaign_links where campaign_id = %s", id_a)
    assert n_links == 2


def test_ltwm_and_archive_merge_reversed_order(conn):
    """Mismo caso con LTWM primero: el premio sin categoría se reemplaza."""
    from trucho_ingest.db import repo

    id_b = repo.upsert_raw_campaign(conn, _ltwm_litany())
    id_a = repo.upsert_raw_campaign(conn, _archive_litany())
    assert id_a == id_b

    awards = conn.execute(
        "select category, tier from awards where campaign_id = %s", (id_a,)
    ).fetchall()
    assert len(awards) == 1
    assert awards[0]["category"] == "Film"  # la versión con categoría ganó


def test_elojo_and_ltwm_merge_summing_festivals(conn):
    """Colisión El Ojo + LTWM: pieza iberoamericana premiada en ambos festivales."""
    from trucho_ingest.db import repo

    id_a = repo.upsert_raw_campaign(conn, _elojo_juntos())
    id_b = repo.upsert_raw_campaign(conn, _ltwm_juntos())
    assert id_a == id_b

    assert _count(conn, "select count(*) as n from campaigns") == 1
    # premios de festivales DISTINTOS se suman, no se pisan
    awards = conn.execute(
        """
        select f.slug as festival, a.tier from awards a
        join festivals f on f.id = a.festival_id
        where a.campaign_id = %s order by 1
        """,
        (id_a,),
    ).fetchall()
    assert [(a["festival"], a["tier"]) for a in awards] == [
        ("cannes", "gold"),
        ("el-ojo", "silver"),
    ]
    # el país que trajo El Ojo se conserva
    country = conn.execute(
        "select country from campaigns where id = %s", (id_a,)
    ).fetchone()["country"]
    assert country == "AR"


def test_fuzzy_title_variation_still_merges(conn):
    """"The Whopper Detour" vs "WHOPPER DETOUR": mismo registro."""
    from trucho_ingest.db import repo

    a = _archive_litany().model_copy(
        update={"title": "The Whopper Detour", "brand": "Burger King", "year": 2019}
    )
    a.awards[0].year = 2019
    b = _ltwm_litany().model_copy(
        update={"title": "WHOPPER DETOUR", "brand": "BURGER KING", "year": 2019}
    )
    b.awards[0].year = 2019

    id_a = repo.upsert_raw_campaign(conn, a)
    id_b = repo.upsert_raw_campaign(conn, b)
    assert id_a == id_b
    assert _count(conn, "select count(*) as n from campaigns") == 1


def test_different_campaigns_stay_separate(conn):
    """Misma marca y año, títulos distintos: dos campañas."""
    from trucho_ingest.db import repo

    a = _elojo_juntos()
    b = _elojo_juntos().model_copy(update={"title": "Otra idea distinta"})
    id_a = repo.upsert_raw_campaign(conn, a)
    id_b = repo.upsert_raw_campaign(conn, b)
    assert id_a != id_b
    assert _count(conn, "select count(*) as n from campaigns") == 2
