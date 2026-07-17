"""CLI de Trucho: trucho db migrate | ingest | enrich | embed | stats | show."""

import json
import sys

import typer

app = typer.Typer(
    name="trucho",
    help="Pipeline de ingesta de Trucho: scrape → enrich → embed → load.",
    no_args_is_help=True,
)
db_app = typer.Typer(help="Operaciones de base de datos.", no_args_is_help=True)
app.add_typer(db_app, name="db")


def _err(message: str) -> None:
    typer.secho(f"✗ {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


@db_app.command("migrate")
def db_migrate() -> None:
    """Aplica las migraciones SQL pendientes."""
    from .db import repo

    try:
        with repo.connect() as conn:
            executed = repo.migrate(conn)
    except Exception as e:  # noqa: BLE001
        _err(str(e))
    if executed:
        for name in executed:
            typer.secho(f"✓ aplicada {name}", fg=typer.colors.GREEN)
    else:
        typer.echo("Sin migraciones pendientes.")


@app.command()
def ingest(
    source: str = typer.Argument(help="Fuente a scrapear (ej: elojo)."),
    year: int | None = typer.Option(None, help="Año del festival (default: último)."),
    category: str | None = typer.Option(
        None, help="Filtro de categoría por substring de URL (ej: film)."
    ),
    limit: int | None = typer.Option(None, help="Máximo de campañas a ingerir."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Muestra lo scrapeado sin escribir a la DB."
    ),
) -> None:
    """Scrapea una fuente y hace upsert de campañas crudas a Postgres."""
    from .db import repo
    from .scrapers import get_scraper

    try:
        scraper = get_scraper(source)
    except KeyError as e:
        _err(str(e.args[0]))

    count = 0
    if dry_run:
        for raw in scraper.scrape(year=year, category=category, limit=limit):
            typer.echo(json.dumps(raw.model_dump(mode="json"), ensure_ascii=False))
            count += 1
        typer.secho(f"✓ {count} campañas scrapeadas (dry-run, DB intacta)", fg="green")
        return

    try:
        with repo.connect() as conn:
            for raw in scraper.scrape(year=year, category=category, limit=limit):
                repo.upsert_raw_campaign(conn, raw)
                count += 1
                if count % 10 == 0:
                    conn.commit()
                    typer.echo(f"  …{count} campañas")
            conn.commit()
    except Exception as e:  # noqa: BLE001
        _err(f"Ingesta falló tras {count} campañas: {e}")
    typer.secho(f"✓ {count} campañas ingeridas desde '{source}'", fg="green")


@app.command()
def enrich(
    limit: int | None = typer.Option(None, help="Máximo de campañas a analizar."),
) -> None:
    """Genera el análisis LLM (summary, insight, ejecución…) de campañas pendientes."""
    from .db import repo
    from .enrichment.analyze import EnrichmentError, analyze_campaign

    try:
        with repo.connect() as conn:
            pending = repo.pending_enrichment(conn, limit=limit)
            if not pending:
                typer.echo("No hay campañas pendientes de enrichment.")
                return
            typer.echo(f"{len(pending)} campañas pendientes…")
            ok, failed = 0, 0
            for row in pending:
                campaign = dict(row)
                for key in ("awards", "agencies"):
                    if isinstance(campaign.get(key), str):
                        campaign[key] = json.loads(campaign[key])
                try:
                    analysis = analyze_campaign(campaign)
                    repo.save_analysis(conn, campaign["id"], analysis)
                    conn.commit()
                    ok += 1
                    typer.secho(f"✓ {campaign['slug']}", fg="green")
                except EnrichmentError as e:
                    conn.rollback()
                    failed += 1
                    typer.secho(f"✗ {campaign['slug']}: {e}", fg="red", err=True)
    except Exception as e:  # noqa: BLE001
        _err(str(e))
    typer.echo(f"Enrichment: {ok} ok, {failed} fallidas.")
    if failed and not ok:
        sys.exit(1)


@app.command()
def embed(
    limit: int | None = typer.Option(None, help="Máximo de campañas a embeber."),
) -> None:
    """Calcula embeddings bge-m3 de campañas ya analizadas."""
    from .config import EMBEDDING_MODEL
    from .db import repo
    from .enrichment.embed import embed_text, embedding_content

    try:
        with repo.connect() as conn:
            pending = repo.pending_embedding(conn, limit=limit)
            if not pending:
                typer.echo("No hay campañas pendientes de embedding.")
                return
            typer.echo(f"{len(pending)} campañas pendientes…")
            for row in pending:
                content = embedding_content(
                    row["summary"] or "", row["insight"] or "", row["execution"] or ""
                )
                vector = embed_text(content)
                repo.save_embedding(conn, row["id"], content, vector, EMBEDDING_MODEL)
                conn.commit()
                typer.secho(f"✓ {row['slug']}", fg="green")
    except Exception as e:  # noqa: BLE001
        _err(str(e))


@app.command()
def stats() -> None:
    """Muestra la cobertura de la DB: campañas por festival, año y país."""
    from .db import repo

    try:
        with repo.connect() as conn:
            data = repo.stats(conn)
    except Exception as e:  # noqa: BLE001
        _err(str(e))

    typer.secho("— Trucho: cobertura de la base —", bold=True)
    typer.echo(f"Campañas:   {data['total']}")
    typer.echo(f"Analizadas: {data['enriched']}")
    typer.echo(f"Embebidas:  {data['embedded']}")
    if data["by_festival"]:
        typer.echo("\nPor festival/año:")
        for r in data["by_festival"]:
            typer.echo(f"  {r['name']} {r['year']}: {r['campaigns']}")
    if data["by_country"]:
        typer.echo("\nPor país:")
        for r in data["by_country"]:
            typer.echo(f"  {r['country']}: {r['campaigns']}")


@app.command()
def show(slug: str = typer.Argument(help="Slug de la campaña.")) -> None:
    """Muestra la ficha completa de una campaña."""
    from .db import repo

    try:
        with repo.connect() as conn:
            campaign = repo.get_campaign(conn, slug)
    except Exception as e:  # noqa: BLE001
        _err(str(e))
    if campaign is None:
        _err(f"No existe la campaña '{slug}'.")
    typer.echo(json.dumps(campaign, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    app()
