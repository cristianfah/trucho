# Trucho

> Base de conocimiento open source de campañas publicitarias premiadas, consultable en lenguaje natural vía [MCP](https://modelcontextprotocol.io).

**Trucho** es una herramienta para creativos publicitarios: una base de datos de campañas premiadas y finalistas de los principales festivales del mundo e Iberoamérica (Cannes, El Ojo, FIAP, El Sol, ACHAP…), con análisis estructurado por campaña — idea, insight, ejecución, resultados y palmarés — consultable desde Claude, ChatGPT, Hermes o cualquier cliente compatible con MCP.

**Caso de uso central:** contás tu idea en lenguaje natural (*"una campaña donde la marca convierte quejas de clientes en el propio anuncio"*) y Trucho devuelve campañas similares ya realizadas, con su análisis completo y links a los cases.

¿Por qué *Trucho*? Guiño a las piezas trucho/spec que inundan los festivales. La herramienta ayuda a no repetir lo ya hecho — o a robarlo mejor.

## Principio clave: la base de datos ES el producto

Cada registro es útil por sí solo, sin abrir links externos:

- Título, marca, agencia(s), país, año
- Descripción completa de la idea, insight, mecánica/ejecución, resultados
- Premios: festival, año, categoría, nivel (Grand Prix, Oro, Plata, Bronce, Shortlist)
- Tags temáticos y de industria
- Links externos al case film / cobertura
- Embeddings para búsqueda semántica

**Qué NO guardamos:** assets audiovisuales (solo links) ni texto copiado verbatim de las fuentes. Los análisis se redactan con LLM en palabras propias a partir de información pública. Los hechos (quién ganó qué) no son protegibles por copyright; el análisis redactado es contenido original del proyecto.

## Arquitectura

```
trucho/
├── apps/
│   ├── mcp-server/          # Servidor MCP en TypeScript (Fase 2)
│   └── ingestion/           # Pipeline de ingesta en Python
├── packages/
│   ├── schema/              # Schemas Zod (espejo de los Pydantic de ingestion)
│   └── db/                  # Migraciones SQL
├── exports/                 # Skill bundles generados (Fase 3)
└── docs/
```

- **DB:** PostgreSQL 16 + pgvector (Supabase free tier para el MVP)
- **Ingesta:** Python 3.12 + uv, httpx + selectolax, `anthropic` SDK para enrichment
- **Embeddings:** `BAAI/bge-m3` (local, multilingüe ES/PT/EN)
- **MCP server:** TypeScript + `@modelcontextprotocol/sdk` (Fase 2)
- **Search:** híbrida — BM25 (tsvector) + vector (pgvector HNSW), fusión RRF

Trucho **nunca corre LLMs propios en producción**: el LLM lo pone el usuario (su cuenta de Claude/ChatGPT). Solo la ingesta usa LLM, con la API key de quien corre el pipeline.

## Quick start (pipeline de ingesta)

Requisitos: [uv](https://docs.astral.sh/uv/), PostgreSQL 16 con pgvector (o un proyecto Supabase), una API key de Anthropic.

```bash
cd apps/ingestion
uv sync                      # instala dependencias
cp ../../.env.example ../../.env   # completar DATABASE_URL y ANTHROPIC_API_KEY

uv run trucho db migrate     # aplica migraciones
uv run trucho ingest elojo --year 2025 --limit 30   # scrape El Ojo
uv run trucho enrich         # análisis LLM (summary, insight, ejecución…)
uv run trucho embed          # embeddings bge-m3 (requiere: uv sync --extra embed)
uv run trucho stats          # cobertura de la DB
uv run trucho show <slug>    # ficha completa de una campaña
```

## Scraping ético

- Se respeta `robots.txt` de cada fuente
- Rate limiting: 1 request cada 2 segundos por dominio
- User-Agent identificable con link a este repo
- Sin bypass de paywalls; solo información pública
- Trazabilidad completa en la tabla `sources`

## Roadmap

- **Fase 1 — Fundación** *(en curso)*: scaffold, migraciones, scraper El Ojo, enrichment end-to-end
- **Fase 2 — MCP**: servidor con `search_campaigns`, `get_campaign`, `find_similar`, `list_awards`, `stats`
- **Fase 3 — Escala**: más fuentes (FIAP, El Sol, ACHAP), dedupe cross-fuente, skill bundle export
- **Fase 4 — Comunidad**: guías de contribución, templates, CI completo

## Licencia

[AGPL-3.0](LICENSE)
