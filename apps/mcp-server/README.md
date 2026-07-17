# @trucho/mcp-server

Servidor MCP de Trucho — **Fase 2, aún no implementado**.

Expondrá cinco herramientas read-only sobre la base de campañas:

| Tool | Qué hace |
|---|---|
| `search_campaigns(query, filters?)` | Búsqueda híbrida BM25 + vector con fusión RRF |
| `get_campaign(slug \| id)` | Ficha completa: análisis, premios, links |
| `find_similar(idea_text)` | Describís tu idea y devuelve campañas similares rankeadas |
| `list_awards(festival, year?)` | Palmarés de un festival/año |
| `stats()` | Cobertura de la DB |

Stack previsto: TypeScript + `@modelcontextprotocol/sdk`, Node 20+, deploy en Railway o Fly.io. Read-only, sin auth para lectura, rate limiting básico.

Decisión pendiente (documentar en `docs/` al implementar): dónde correr el embedding de `find_similar` (bge-m3 vía ONNX en el server vs. endpoint de embedding aparte).
