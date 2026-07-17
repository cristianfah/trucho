# Fuente: dataset "Cannes Lions Film Winners 1954-2000" (Internet Archive)

**Item:** https://archive.org/details/cannes-lions-advertising-film-winners · **Slug:** `archive-org-cla` · **Prioridad:** 1 (histórico)

## Qué es

Dataset público consolidado de los ganadores de **Film** de Cannes Lions 1954–2000: el registro más completo de ese período publicado en internet abierto. Descarga directa desde Internet Archive (robots.txt de archive.org permite `/download/`).

Archivo principal: `Cannes Lions Film 1954-2000.xlsx` (~450 KB) — una hoja por año, columnas `Award / Category / Brand / Product / Title / Agency / City / Production / City / Country / Source / Comments`. El item incluye además `skeleton.txt` (conteos por país/nivel/año), `sources.txt` (catálogo de los IDs de fuente citados por fila) y `changelog.txt`.

## Estrategia: importer, no scraper

`trucho ingest archive-org-cla` descarga el Excel una vez (cache local), lo parsea con openpyxl y carga con `source_site='archive-org-cla'`. Mismo contrato que un scraper (`RawCampaign`), análisis en null — lo llena el enrichment.

### Detalles de parseo

- **Headers por nombre, no por posición**: algunos años (ej. 1999) agregan la columna `Entrant`. Las dos columnas `City` se desambiguan por orden (agencia / productora).
- **Award vacío hereda el de la fila anterior** (convención del Excel para piezas consecutivas del mismo premio).
- **Hojas ignoradas**: `1958 (Collection of Films)` (inscripciones, no ganadores), `Indeterminate Year`, `Unconfirmed`.
- **Filas sin pieza** (premios a agencias/personas: `Agency of the Year`, `Palme d'Or` a productoras, `Journalists`) se descartan.
- **Mapeo de tiers** (el sistema de premios cambió en 1969 a Lion d'Or/Argent/Bronze):
  - `Grand Prix` → `grand_prix`
  - `Gold`, `Gold Medal`, `1st`, `1` → `gold`
  - `Silver`, `2nd`, `Runner-up` → `silver`
  - `Bronze`, `3rd` → `bronze`
  - `Diploma*`, `Mention*`, `Shortlist`, puestos 4+ → `shortlist`
  - Premios especiales (`Special Jury Prize`, `Coppa di Venezia`, `National Prize`…) → `winner`
- `category` se guarda como `Film — {Category}` (o `Film` si no hay) para no chocar con categorías de otros festivales.

## Advertencias del propio dataset → `sources.confidence`

Las notas del item documentan problemas conocidos; por eso el schema tiene el campo `confidence` en `sources` (migración `0002`):

- **Error de fechas propagado en los ganadores de 1999–2000** ("A dating error has propagated throughout the various iterations of CLA for winners beyond 1998"). Todas las filas de esos años se cargan con `confidence = 'low'`.
- Premios con `?` o `(DISPUTED)` → `confidence = 'low'`.
- El registro es **incompleto por naturaleza** (así lo declara el propio dataset); las entradas entre paréntesis indican incertidumbre.
- Los music videos (premiados desde los 80) fueron excluidos deliberadamente del Excel.

## Solapamiento esperado con LTWM

LTWM y este dataset cubren las mismas campañas 1954–2000. Verificado en vivo con el año 1999: 119 registros de LTWM + 123 del dataset → 137 campañas únicas, 103 fusionadas desde ambas fuentes. El dedupe cross-fuente (slug + fuzzy con trigram) fusiona sumando premios y completando campos; el premio sin categoría de LTWM se reemplaza por el mismo premio con categoría del dataset.
