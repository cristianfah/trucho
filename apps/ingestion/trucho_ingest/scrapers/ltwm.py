"""Scraper de Love The Work More (lovetheworkmore.com).

OJO: NO confundir con lovethework.com (el archivo pago de Cannes, de Informa).
LTWM es un proyecto independiente y gratuito que compila metadata de todos los
ganadores de Leones desde 1954, con links a fuentes libres (YouTube, sitios de
agencias, Clios...). Ver docs/sources/ltwm.md.

Estructura (WordPress + Divi, HTML estático, API wp-json abierta):

    /wp-json/wp/v2/pages           ← mapa título ("2019") → URL de la página
    /2019-2/                       ← página anual

En cada página anual, los <p> dentro de #main-content siguen el patrón:

    <p><strong>GRAND PRIX / TITANIUM</strong></p>   ← nivel (máximo León del año)
    <p><a href="LINK_EXTERNO">TITLE – BRAND (AGENCY CITY)</a></p>

La página histórica /1954-1999/ usa el mismo patrón con el año adelante:

    1959 – TIRED DOG – CALO PET FOOD CO. (FOOTE, CONE & BELDING CHICAGO)

El sitio muestra cada trabajo según el MÁXIMO León ganado ese año. La categoría
del León solo aparece en años recientes y solo en los Grand Prix, con el
formato "[TITANIUM] TITLE – BRAND (AGENCY)"; en el resto de las entradas
category queda en null (la aporta otra fuente al fusionar, o el enrichment)."""

import re
from collections.abc import Iterator

from selectolax.parser import HTMLParser, Node

from ..models import (
    Award,
    AwardTier,
    CampaignAgency,
    CampaignLink,
    LinkKind,
    RawCampaign,
)

SLUG = "ltwm"
FESTIVAL_SLUG = "cannes"
BASE_URL = "https://lovetheworkmore.com"
PAGES_API = f"{BASE_URL}/wp-json/wp/v2/pages?per_page=100&_fields=title,link"

_TIER_MAP = [
    ("GRAND PRIX", AwardTier.GRAND_PRIX),
    ("TITANIUM", AwardTier.GRAND_PRIX),
    ("GOLD", AwardTier.GOLD),
    ("SILVER", AwardTier.SILVER),
    ("BRONZE", AwardTier.BRONZE),
    ("SHORTLIST", AwardTier.SHORTLIST),
]

# TITLE – BRAND (AGENCY CITY) · separador: en dash, em dash o guion
_DASH = r"\s+[–—-]\s+"
_ENTRY_RE = re.compile(
    r"^(?P<body>.+?)(?:\s*\((?P<agency>[^()]+)\))?\s*$", re.DOTALL
)
_HIST_YEAR_RE = re.compile(rf"^(?P<year>19\d\d|20\d\d){_DASH}(?P<rest>.+)$", re.DOTALL)
# En años recientes los Grand Prix anteponen la categoría del León: "[TITANIUM] …"
_CATEGORY_RE = re.compile(r"^\[(?P<category>[^\]]+)\]\s*(?P<rest>.+)$", re.DOTALL)


def _tier_from_header(text: str) -> AwardTier | None:
    upper = text.strip().upper()
    for token, tier in _TIER_MAP:
        if token in upper and len(upper) < 40:
            return tier
    return None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_entry_text(text: str) -> tuple[str, str, str | None, str | None] | None:
    """Parsea "[CATEGORY] TITLE – BRAND (AGENCY)" → (title, brand, agency, category)."""
    text = text.strip()
    category = None
    cat_match = _CATEGORY_RE.match(text)
    if cat_match:
        category = _clean(cat_match.group("category")).title()
        text = cat_match.group("rest")

    m = _ENTRY_RE.match(text.strip())
    if not m:
        return None
    body = _clean(m.group("body"))
    agency = _clean(m.group("agency")) if m.group("agency") else None

    parts = [p for p in re.split(_DASH, body) if p.strip()]
    if len(parts) >= 2:
        # la marca es el último segmento; el título puede contener guiones
        title = _clean(" – ".join(parts[:-1]))
        brand = _clean(parts[-1])
    elif len(parts) == 1 and agency:
        # entrada sin título explícito (ej: "1984 – APPLE COMPUTER (TBWA...)")
        title = brand = _clean(parts[0])
    else:
        return None

    if not title or not brand:
        return None
    return title, brand, agency, category


def _external_link(p: Node) -> str | None:
    a = p.css_first("a[href]")
    if a is None:
        return None
    href = (a.attributes.get("href") or "").strip()
    if href.startswith("http") and "lovetheworkmore.com" not in href:
        return href
    return None


def _build_campaign(
    title: str,
    brand: str,
    agency: str | None,
    year: int,
    tier: AwardTier,
    link: str | None,
    source_url: str,
    category: str | None = None,
) -> RawCampaign:
    links = [CampaignLink(kind=LinkKind.FESTIVAL_PAGE, url=source_url)]
    if link:
        links.insert(0, CampaignLink(kind=LinkKind.CASE_FILM, url=link))
    agency_txt = f" Agencia: {agency}." if agency else ""
    category_txt = f" Categoría: {category}." if category else ""
    return RawCampaign(
        title=title,
        brand=brand,
        year=year,
        country=None,  # LTWM no publica país
        agencies=[CampaignAgency(name=agency)] if agency else [],
        awards=[Award(festival=FESTIVAL_SLUG, year=year, category=category, tier=tier)],
        links=links,
        raw_text=(
            f"Festival: Cannes Lions {year}. Máximo León ganado: {tier.value}."
            f"{category_txt} Pieza: {title}. Marca: {brand}.{agency_txt}"
        ),
        source_site=SLUG,
        source_url=source_url,
    )


def parse_year_page(html: str, year: int, source_url: str) -> list[RawCampaign]:
    """Parsea una página anual moderna (2000-2026)."""
    campaigns: list[RawCampaign] = []
    tier: AwardTier | None = None
    for p in _content_paragraphs(html):
        text = _clean(p.text())
        if not text:
            continue
        if p.css_first("strong") is not None and _tier_from_header(text) is not None:
            tier = _tier_from_header(text)
            continue
        if tier is None:
            continue
        parsed = _parse_entry_text(text)
        if parsed is None:
            continue
        title, brand, agency, category = parsed
        campaigns.append(
            _build_campaign(
                title, brand, agency, year, tier, _external_link(p), source_url,
                category=category,
            )
        )
    return campaigns


def parse_historic_page(html: str, source_url: str) -> list[RawCampaign]:
    """Parsea /1954-1999/: mismas reglas, con el año adelante de cada entrada."""
    campaigns: list[RawCampaign] = []
    tier: AwardTier | None = None
    for p in _content_paragraphs(html):
        text = _clean(p.text())
        if not text:
            continue
        if p.css_first("strong") is not None and _tier_from_header(text) is not None:
            tier = _tier_from_header(text)
            continue
        m = _HIST_YEAR_RE.match(text)
        if m is None or tier is None:
            continue
        rest = m.group("rest").strip()
        if rest.upper().startswith("NO WINNER"):
            continue
        parsed = _parse_entry_text(rest)
        if parsed is None:
            continue
        title, brand, agency, category = parsed
        campaigns.append(
            _build_campaign(
                title, brand, agency, int(m.group("year")), tier,
                _external_link(p), source_url, category=category,
            )
        )
    return campaigns


def _content_paragraphs(html: str):
    tree = HTMLParser(html)
    content = tree.css_first("#main-content") or tree.css_first("body")
    if content is None:
        return []
    return content.css("p")


HISTORIC_TITLE = "1954-1999"


def year_pages(pages_json: list[dict]) -> dict[str, str]:
    """Mapa título → URL desde la API wp-json ("2019" → /2019-2/)."""
    result: dict[str, str] = {}
    for page in pages_json:
        title = _clean(page.get("title", {}).get("rendered", ""))
        link = page.get("link", "")
        if re.fullmatch(r"(19|20)\d\d(-(19|20)\d\d)?", title) and link:
            result[title] = link
    return result


def _year_for_title(title: str) -> int:
    """"2019" → 2019; "2020-2021" → 2021 (edición combinada post-pandemia)."""
    return max(int(y) for y in re.findall(r"(?:19|20)\d\d", title))


def ingestion_order(titles: list[str]) -> list[str]:
    """Prioridad de ingesta: 2015-2025 primero, después el resto hacia atrás."""

    def key(title: str) -> tuple[int, int]:
        year = _year_for_title(title)
        priority = 0 if 2015 <= year <= 2025 else 1
        return (priority, -year)

    return sorted((t for t in titles if t != HISTORIC_TITLE), key=key) + (
        [HISTORIC_TITLE] if HISTORIC_TITLE in titles else []
    )


class LtwmScraper:
    slug = SLUG

    def __init__(self, client=None) -> None:
        from ..http import EthicalClient

        self._client = client or EthicalClient()

    def scrape(
        self,
        year: int | None = None,
        category: str | None = None,  # LTWM no publica categorías; se ignora
        limit: int | None = None,
    ) -> Iterator[RawCampaign]:
        pages = year_pages(self._client.get(PAGES_API).json())

        if year is not None:
            titles = [
                t for t in pages
                if (t == HISTORIC_TITLE and year <= 1999)
                or (t != HISTORIC_TITLE and _year_for_title(t) == year)
                or (t != HISTORIC_TITLE and "-" in t and str(year) in t)
            ]
        else:
            titles = ingestion_order(list(pages))

        count = 0
        for title in titles:
            url = pages[title]
            html = self._client.get(url).text
            if title == HISTORIC_TITLE:
                found = parse_historic_page(html, url)
                if year is not None:
                    found = [c for c in found if c.year == year]
            else:
                found = parse_year_page(html, _year_for_title(title), url)
            for campaign in found:
                yield campaign
                count += 1
                if limit is not None and count >= limit:
                    return
