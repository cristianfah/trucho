# Fuente: El Ojo de Iberoamérica

**Sitio:** https://www.elojodeiberoamerica.com · **Slug:** `elojo` · **Prioridad:** 1 (foco Iberoamérica)

## Por qué es el scraper #1 (y no Love The Work More)

Evaluamos las fuentes de prioridad 1 antes de escribir código (2026-07):

| Fuente | Veredicto |
|---|---|
| **Love The Work More** (lovethework.com) | ❌ Descartada como primera fuente: su `robots.txt` bloquea explícitamente crawlers de AI (lista `Anthropic-ai`, `ClaudeBot`, `GPTBot`… con `Disallow: /`) y el grueso del contenido está detrás de login/paywall de Cannes Lions. Scrapearlo violaría nuestra política de scraping ético. |
| **El Ojo de Iberoamérica** | ✅ **Elegida.** Sin `robots.txt` (todo permitido). Palmarés completo 2012–2025 publicado en HTML estático de WordPress. Datos ricos y consistentes. Además es EL festival de referencia de Iberoamérica, el foco del proyecto. |
| FIAP (fiaponline.net) | Pendiente de evaluar en detalle (robots.txt extenso con lista de bots bloqueados; revisar en Fase 3). |

## Estrategia técnica: HTML estático (httpx + selectolax)

No hace falta Playwright ni hay API oculta relevante: el contenido está completo en el HTML servido. Es WordPress con la API REST `wp-json` abierta, pero las páginas de ganadores son páginas estáticas cuyo contenido no está estructurado en la API, así que parseamos el HTML directamente.

### Estructura del sitio

```
/premio/finalistas-y-ganadores-{year}/              ← hub del año (2012–2025)
/premio/finalistas-y-ganadores-{year}/el-ojo-{cat}-{year}/  ← página por categoría
```

Excepción: 2017 usa el slug `finalistas-ganadores-2017` (sin la "y").

Categorías por año: Film, Gráfica, Radio & Audio, Vía Pública, Digital & Social, Media, Directo, Experiencia de Marca & Activación, PR, Design, Sustentable, Sports, Contenido, El Tercer Ojo, Innovación, Creative Data, Creative Commerce, Eficacia, y más (varían por año).

### Patrón de parseo

Dentro de `div.entry-content`, los `<p>` siguen una máquina de estados:

```html
<p><strong><u>GRAN OJO FILM</u></strong></p>        ← nivel del premio vigente
<p><em><u>Alimentos y bebidas – FL1</u></em></p>    ← subcategoría vigente
<p>“<a href="https://www.latinspots.com/...">Título</a>”,
   de AGENCIA (País) para MARCA de ANUNCIANTE.
   Prod.: ... Realizador: ... País: X.</p>          ← una pieza premiada
</p>
```

Claves:

- Los niveles (`GRAN OJO …`, `ORO`, `PLATA`, `BRONCE`) aplican a **todas las piezas siguientes** hasta el próximo header — dos platas seguidas comparten un solo header `PLATA`.
- Casi todas las piezas linkean su página en **LatinSpots**, que usamos como link `case_film`.
- El campo final `País: X` es el país de la campaña; si falta, usamos el país de la primera agencia.
- Mapeo de niveles: `GRAN OJO → grand_prix`, `ORO → gold`, `PLATA → silver`, `BRONCE → bronze`, `FINALISTA/SHORTLIST → shortlist`.

### Dedupe intra-fuente

La misma pieza puede ganar en varias categorías (ej. el Gran Ojo también lleva Oro en su subcategoría). El slug `marca-titulo-año` fusiona esos registros en una campaña con N premios.

## Scraping ético aplicado

- `robots.txt` verificado en cada request (`EthicalClient`)
- 1 request cada 2 segundos por dominio
- User-Agent: `trucho-bot/0.1 (+https://github.com/cristianfah/trucho)`
- Solo contenido público; los assets quedan en su fuente (links a LatinSpots)

## Limitaciones conocidas

- El texto por pieza es breve (créditos + categoría): el enrichment LLM trabaja con poco contexto para piezas oscuras. Mitigación futura: cruzar con la página de LatinSpots de cada pieza (tienen sinopsis) y/o transcripción del case film.
- Años ≤2016 pueden variar el markup; el parser está validado con 2025. Revisar fixture por año antes de ingestas históricas masivas.
