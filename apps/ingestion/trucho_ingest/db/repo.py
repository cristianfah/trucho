"""Repositorio Postgres del pipeline.

Regla de upsert: un re-scrape actualiza los HECHOS (premios, links, fuentes)
pero nunca pisa el ANÁLISIS ya generado (summary, insight...). El análisis
solo lo escribe `save_analysis`.
"""

import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from ..config import MIGRATIONS_DIR, database_url
from ..models import CampaignAnalysis, RawCampaign
from ..normalize import campaign_slug, is_same_campaign


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url(), row_factory=dict_row)


# ---------------------------------------------------------------------------
# Migraciones
# ---------------------------------------------------------------------------

def migrate(conn: psycopg.Connection) -> list[str]:
    """Aplica las migraciones pendientes de packages/db/migrations, en orden."""
    conn.execute(
        """
        create table if not exists schema_migrations (
          filename text primary key,
          applied_at timestamptz not null default now()
        )
        """
    )
    applied = {
        r["filename"]
        for r in conn.execute("select filename from schema_migrations").fetchall()
    }
    executed: list[str] = []
    for path in sorted(Path(MIGRATIONS_DIR).glob("*.sql")):
        if path.name in applied:
            continue
        conn.execute(path.read_text())
        conn.execute(
            "insert into schema_migrations (filename) values (%s)", (path.name,)
        )
        executed.append(path.name)
    conn.commit()
    return executed


# ---------------------------------------------------------------------------
# Load: upsert de campañas crudas
# ---------------------------------------------------------------------------

def find_matching_campaign(conn: psycopg.Connection, raw: RawCampaign) -> str | None:
    """Busca una campaña existente que sea LA MISMA que `raw` (dedupe cross-fuente).

    1. Match exacto por slug (brand + título normalizado + año).
    2. Match fuzzy: candidatos por similitud trigram de marca y título con
       ventana de año ±1 (LTWM y Archive traen las mismas campañas 1954-2000;
       LTWM y El Ojo se solapan en piezas iberoamericanas premiadas en ambos).
    """
    slug = campaign_slug(raw.brand, raw.title, raw.year)
    row = conn.execute("select id from campaigns where slug = %s", (slug,)).fetchone()
    if row is not None:
        return row["id"]

    candidates = conn.execute(
        """
        select id, title, brand, year from campaigns
        where (year is null or %(year)s::int is null
               or year between %(year)s - 1 and %(year)s + 1)
          and (similarity(brand, %(brand)s) > 0.3
               or similarity(title, %(title)s) > 0.3)
        limit 50
        """,
        {"year": raw.year, "brand": raw.brand, "title": raw.title},
    ).fetchall()
    for c in candidates:
        if is_same_campaign(
            raw.brand, raw.title, raw.year, c["brand"], c["title"], c["year"]
        ):
            return c["id"]
    return None


def upsert_raw_campaign(conn: psycopg.Connection, raw: RawCampaign) -> str:
    """Inserta o fusiona una campaña cruda. Devuelve el campaign_id.

    Si la campaña ya existe (misma u otra fuente), se FUSIONA: se suman
    premios/links/agencias/fuentes y se completan campos vacíos, sin duplicar
    la campaña ni pisar el análisis ya generado.
    """
    existing_id = find_matching_campaign(conn, raw)
    if existing_id is not None:
        conn.execute(
            """
            update campaigns set
              country = coalesce(country, %s),
              year = coalesce(year, %s)
            where id = %s
            """,
            (raw.country, raw.year, existing_id),
        )
        campaign_id = existing_id
    else:
        row = conn.execute(
            """
            insert into campaigns (slug, title, brand, year, country)
            values (%s, %s, %s, %s, %s)
            returning id
            """,
            (campaign_slug(raw.brand, raw.title, raw.year), raw.title, raw.brand,
             raw.year, raw.country),
        ).fetchone()
        campaign_id = row["id"]

    for agency in raw.agencies:
        arow = conn.execute(
            """
            insert into agencies (name, country) values (%s, %s)
            on conflict (name) do update set
              country = coalesce(agencies.country, excluded.country)
            returning id
            """,
            (agency.name, agency.country),
        ).fetchone()
        conn.execute(
            """
            insert into campaign_agencies (campaign_id, agency_id, role)
            values (%s, %s, %s) on conflict do nothing
            """,
            (campaign_id, arow["id"], agency.role.value),
        )

    for award in raw.awards:
        # Fusión de premios cross-fuente: un premio sin categoría (ej: LTWM,
        # que solo publica el máximo León) NO debe duplicar el mismo premio
        # ya cargado con categoría (ej: dataset de Archive).
        if award.category is None:
            conn.execute(
                """
                insert into awards (campaign_id, festival_id, year, category, tier)
                select %(cid)s, f.id, %(year)s, null, %(tier)s
                from festivals f
                where f.slug = %(festival)s
                  and not exists (
                    select 1 from awards a
                    where a.campaign_id = %(cid)s and a.festival_id = f.id
                      and a.year = %(year)s and a.tier = %(tier)s
                  )
                """,
                {"cid": campaign_id, "year": award.year,
                 "tier": award.tier.value, "festival": award.festival},
            )
        else:
            conn.execute(
                """
                insert into awards (campaign_id, festival_id, year, category, tier)
                select %s, f.id, %s, %s, %s from festivals f where f.slug = %s
                on conflict do nothing
                """,
                (campaign_id, award.year, award.category, award.tier.value,
                 award.festival),
            )
            # si antes entró el mismo premio sin categoría, ahora sobra
            conn.execute(
                """
                delete from awards a using festivals f
                where a.festival_id = f.id and f.slug = %s
                  and a.campaign_id = %s and a.year = %s and a.tier = %s
                  and a.category is null
                """,
                (award.festival, campaign_id, award.year, award.tier.value),
            )

    for link in raw.links:
        conn.execute(
            """
            insert into campaign_links (campaign_id, kind, url)
            values (%s, %s, %s) on conflict do nothing
            """,
            (campaign_id, link.kind.value, link.url),
        )

    conn.execute(
        """
        insert into sources (campaign_id, source_site, source_url, raw_text, confidence)
        values (%s, %s, %s, %s, %s)
        on conflict (campaign_id, source_site, source_url) do update set
          raw_text = excluded.raw_text,
          confidence = excluded.confidence,
          scraped_at = now()
        """,
        (campaign_id, raw.source_site, raw.source_url, raw.raw_text,
         raw.confidence.value),
    )

    return campaign_id


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

def pending_enrichment(conn: psycopg.Connection, limit: int | None = None) -> list[dict]:
    """Campañas sin análisis, con su texto crudo y contexto para el LLM."""
    query = """
        select
          c.id, c.slug, c.title, c.brand, c.year, c.country,
          coalesce(
            (select string_agg(s.raw_text, E'\n---\n')
               from sources s where s.campaign_id = c.id and s.raw_text is not null),
            ''
          ) as raw_text,
          coalesce(
            (select json_agg(json_build_object(
                'festival', f.slug, 'year', a.year,
                'category', a.category, 'tier', a.tier))
               from awards a join festivals f on f.id = a.festival_id
              where a.campaign_id = c.id),
            '[]'
          ) as awards,
          coalesce(
            (select json_agg(json_build_object('name', ag.name))
               from campaign_agencies ca join agencies ag on ag.id = ca.agency_id
              where ca.campaign_id = c.id),
            '[]'
          ) as agencies
        from campaigns c
        where c.description is null
        order by c.year desc nulls last, c.slug
    """
    if limit:
        query += f" limit {int(limit)}"
    return conn.execute(query).fetchall()


def save_analysis(
    conn: psycopg.Connection, campaign_id: str, analysis: CampaignAnalysis
) -> None:
    conn.execute(
        """
        update campaigns set
          summary = %s, description = %s, insight = %s, execution = %s,
          results = %s, industry = %s, language = %s
        where id = %s
        """,
        (
            analysis.summary,
            analysis.description,
            analysis.insight,
            analysis.execution,
            analysis.results,
            analysis.industry.value,
            analysis.language,
            campaign_id,
        ),
    )
    for tag in analysis.tags:
        trow = conn.execute(
            """
            insert into tags (name) values (%s)
            on conflict (name) do update set name = excluded.name
            returning id
            """,
            (tag.strip().lower(),),
        ).fetchone()
        conn.execute(
            """
            insert into campaign_tags (campaign_id, tag_id)
            values (%s, %s) on conflict do nothing
            """,
            (campaign_id, trow["id"]),
        )


def record_analysis_source(
    conn: psycopg.Connection, campaign_id: str, provider: str, model: str
) -> None:
    """Registra en sources qué modelo LLM generó el análisis de la campaña.

    Usa source_site='enrichment' y la URL sintética llm://provider/model; si la
    campaña se re-analiza con otro modelo queda una fila por modelo (historial).
    """
    conn.execute(
        """
        insert into sources (campaign_id, source_site, source_url, raw_text, confidence)
        values (%s, 'enrichment', %s, null, 'normal')
        on conflict (campaign_id, source_site, source_url) do update set
          scraped_at = now()
        """,
        (campaign_id, f"llm://{provider}/{model}"),
    )


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def pending_embedding(conn: psycopg.Connection, limit: int | None = None) -> list[dict]:
    """Campañas con análisis pero sin embedding."""
    query = """
        select c.id, c.slug, c.summary, c.insight, c.execution
        from campaigns c
        left join campaign_embeddings e on e.campaign_id = c.id
        where c.summary is not null and e.campaign_id is null
        order by c.year desc nulls last
    """
    if limit:
        query += f" limit {int(limit)}"
    return conn.execute(query).fetchall()


def save_embedding(
    conn: psycopg.Connection,
    campaign_id: str,
    content: str,
    embedding: list[float],
    model: str,
) -> None:
    conn.execute(
        """
        insert into campaign_embeddings (campaign_id, content, embedding, model)
        values (%s, %s, %s, %s)
        on conflict (campaign_id) do update set
          content = excluded.content,
          embedding = excluded.embedding,
          model = excluded.model
        """,
        (campaign_id, content, json.dumps(embedding), model),
    )


# ---------------------------------------------------------------------------
# Consultas de inspección (CLI)
# ---------------------------------------------------------------------------

def stats(conn: psycopg.Connection) -> dict:
    total = conn.execute("select count(*) as n from campaigns").fetchone()["n"]
    enriched = conn.execute(
        "select count(*) as n from campaigns where description is not null"
    ).fetchone()["n"]
    embedded = conn.execute(
        "select count(*) as n from campaign_embeddings"
    ).fetchone()["n"]
    by_festival = conn.execute(
        """
        select f.name, a.year, count(distinct a.campaign_id) as campaigns
        from awards a join festivals f on f.id = a.festival_id
        group by f.name, a.year order by f.name, a.year desc
        """
    ).fetchall()
    by_country = conn.execute(
        """
        select coalesce(country, '??') as country, count(*) as campaigns
        from campaigns group by country order by campaigns desc limit 15
        """
    ).fetchall()
    return {
        "total": total,
        "enriched": enriched,
        "embedded": embedded,
        "by_festival": by_festival,
        "by_country": by_country,
    }


def get_campaign(conn: psycopg.Connection, slug: str) -> dict | None:
    row = conn.execute(
        "select * from campaigns where slug = %s", (slug,)
    ).fetchone()
    if row is None:
        return None
    row.pop("search_tsv", None)
    row["awards"] = conn.execute(
        """
        select f.slug as festival, a.year, a.category, a.tier
        from awards a join festivals f on f.id = a.festival_id
        where a.campaign_id = %s
        """,
        (row["id"],),
    ).fetchall()
    row["agencies"] = conn.execute(
        """
        select ag.name, ca.role, ag.country
        from campaign_agencies ca join agencies ag on ag.id = ca.agency_id
        where ca.campaign_id = %s
        """,
        (row["id"],),
    ).fetchall()
    row["links"] = conn.execute(
        "select kind, url from campaign_links where campaign_id = %s",
        (row["id"],),
    ).fetchall()
    row["tags"] = [
        r["name"]
        for r in conn.execute(
            """
            select t.name from campaign_tags ct join tags t on t.id = ct.tag_id
            where ct.campaign_id = %s order by t.name
            """,
            (row["id"],),
        ).fetchall()
    ]
    return row
