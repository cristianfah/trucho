# Fuente: Love The Work More

**Sitio:** https://lovetheworkmore.com · **Slug:** `ltwm` · **Prioridad:** 1

## Qué es (y qué NO es)

**No confundir** dos sitios de nombre casi idéntico:

| Sitio | Qué es | Scrapeable |
|---|---|---|
| `lovethework.com` | El archivo **pago** de Cannes Lions, operado por Informa. Paywall + robots.txt que bloquea explícitamente crawlers de AI (`Anthropic-ai`, `ClaudeBot`, `GPTBot`… `Disallow: /`). | ❌ No |
| `lovetheworkmore.com` | Proyecto **independiente y gratuito** que compila metadata de todos los ganadores de Leones desde 1954, con links a fuentes libres (YouTube, sitios de agencias, Clios…). Pide "link donations" a la comunidad. | ✅ Sí |

La evaluación inicial del proyecto descartó "Love The Work" por el robots.txt del sitio de Informa; esta ficha corrige esa decisión para el sitio correcto.

## Evaluación de robots.txt (2026-07)

```
User-agent: *
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php
```

La regla `User-agent: *` solo bloquea `/wp-admin/`. **No hay reglas específicas para UAs de AI** (a diferencia de lovethework.com). El scraping del contenido público está permitido para cualquier agente, incluido nuestro `trucho-bot/1.0 (+https://github.com/cristianfah/trucho)`, con rate limit de 1 req/2s.

## Estrategia técnica: HTML estático + API wp-json

WordPress con tema Divi y la API REST abierta. El descubrimiento de páginas se hace por API (limpio y estable) y el contenido se parsea del HTML:

- `GET /wp-json/wp/v2/pages?per_page=100&_fields=title,link` → mapa `"2019" → /2019-2/`. Los slugs de página no son predecibles (`/704-2/` es 2006), por eso se resuelven por título.
- Páginas anuales 2000–2026, una página combinada `2020-2021` (edición post-pandemia; se atribuye año 2021) y una histórica `1954-1999`.

### Patrón de parseo

Dentro de `#main-content`, los `<p>` en orden del documento:

```html
<p><strong>GRAND PRIX / TITANIUM</strong></p>       ← nivel vigente
<p><a href="LINK_EXTERNO">TITLE – BRAND (AGENCY CITY)</a></p>   ← pieza
```

La página histórica antepone el año: `1959 – TIRED DOG – CALO PET FOOD CO. (FOOTE, CONE & BELDING CHICAGO)`, con líneas `1980 – NO WINNER` que se saltan.

Claves:

- El **último** guion separa la marca (los títulos pueden contener guiones); el paréntesis final es la agencia (con ciudad, sin separar).
- El sitio muestra cada trabajo según el **máximo León ganado ese año**. En años recientes los Grand Prix anteponen la categoría entre corchetes (`[TITANIUM] DOORDASH-ALL-THE-ADS – DOORDASH (…)`), que se extrae como `category`; en el resto de las entradas `category = null` y la aporta otra fuente al fusionar (ej. el dataset de Internet Archive para 1954–2000) — el dedupe elimina el premio sin categoría cuando llega el mismo con categoría.
- El link de cada pieza va a la fuente libre del case (YouTube, Clios, sitio de agencia…) → `kind = case_film`.
- LTWM no publica país → `country = null` (lo completa otra fuente al fusionar).

## Prioridad de ingesta

`2015–2025` primero (descendente), después el resto hacia atrás, y la página histórica al final. Implementado en `ingestion_order()`; `trucho ingest ltwm` sin `--year` sigue ese orden.

## Limitaciones conocidas

- Todo en MAYÚSCULAS → el matching cross-fuente es case-insensitive (slug + fuzzy).
- Sin categoría, sin país, texto mínimo por pieza: LTWM es excelente como **columna vertebral del palmarés + links**, pero el contexto para enrichment viene de las fuentes que se fusionan encima.
- La página `2020-2021` mezcla dos años; se atribuye 2021 (la edición que juzgó ambos).
