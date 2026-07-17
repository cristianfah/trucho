# trucho-ingest

Pipeline de ingesta de Trucho: **scrape → dedupe → enrichment LLM → embed → load**.

```bash
uv sync                       # deps base
uv sync --extra embed         # + sentence-transformers (pesado, solo para `trucho embed`)

uv run trucho db migrate
uv run trucho ingest elojo --year 2025 --limit 30 [--dry-run]
uv run trucho enrich          # necesita ANTHROPIC_API_KEY
uv run trucho embed
uv run trucho stats
uv run trucho show <slug>
```

Configuración vía `.env` en la raíz del repo (ver `.env.example`).

## Estructura

- `scrapers/` — un scraper por fuente (`elojo` implementado; ver `docs/sources/`)
- `enrichment/` — prompt + análisis con Claude (`analyze.py`) y embeddings bge-m3 (`embed.py`)
- `db/repo.py` — migraciones y upserts; un re-scrape nunca pisa análisis ya generado
- `normalize.py` — slugs, países ISO, fuzzy matching para dedupe
- `http.py` — cliente con robots.txt, rate limit 1 req/2s por dominio y UA identificable

## Tests

```bash
uv run pytest      # parser El Ojo (fixture real), normalización, enrichment (LLM falso)
uv run ruff check .
```
