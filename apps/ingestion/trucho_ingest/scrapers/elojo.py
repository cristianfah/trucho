"""Scraper de El Ojo de Iberoamérica (elojodeiberoamerica.com).

Estrategia (ver docs/sources/el-ojo.md): HTML estático de WordPress.
El sitio publica el palmarés completo 2012–2025 en páginas por categoría:

    /premio/finalistas-y-ganadores-{year}/            ← hub del año
    /premio/finalistas-y-ganadores-{year}/el-ojo-film-{year}/  ← categoría

Dentro de cada página de categoría, el patrón de párrafos es:

    <p><strong><u>GRAN OJO FILM</u></strong></p>       ← nivel del premio
    <p><em><u>Alimentos y bebidas – FL1</u></em></p>   ← subcategoría
    <p>“<a href="...">Título</a>”, de AGENCIA (País) para MARCA de
       ANUNCIANTE. Prod.: ... País: X.</p>             ← pieza premiada
"""

import re
from collections.abc import Iterator
from urllib.parse import urljoin

from selectolax.parser import HTMLParser, Node

from ..models import (
    Award,
    AwardTier,
    CampaignAgency,
    CampaignLink,
    LinkKind,
    RawCampaign,
)
from ..normalize import country_to_iso

SLUG = "elojo"
FESTIVAL_SLUG = "el-ojo"
BASE_URL = "https://www.elojodeiberoamerica.com"

# "El clima ideal", de McCann Buenos Aires (Argentina) para BGH de BGH. ...
_ENTRY_RE = re.compile(
    r"^[“\"](?P<title>.+?)[”\"]\s*,?\s+de\s+(?P<agencies>.+?)\s+para\s+(?P<rest>.+)$",
    re.DOTALL,
)
_PAIS_RE = re.compile(r"Pa[ií]s:\s*(?P<country>[^.]+?)\.?\s*$")

_TIER_MAP = [
    ("GRAN OJO", AwardTier.GRAND_PRIX),
    ("GRAN PRIX", AwardTier.GRAND_PRIX),
    ("ORO", AwardTier.GOLD),
    ("PLATA", AwardTier.SILVER),
    ("BRONCE", AwardTier.BRONZE),
    ("FINALISTA", AwardTier.SHORTLIST),
    ("SHORTLIST", AwardTier.SHORTLIST),
]


def _tier_from_header(text: str) -> AwardTier | None:
    upper = text.strip().upper()
    for prefix, tier in _TIER_MAP:
        if upper.startswith(prefix):
            return tier
    return None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_agencies(raw: str) -> list[CampaignAgency]:
    """"McCann BA (Argentina), Initiative" o "W+K São Paulo (Brasil) / W+K BA"."""
    agencies: list[CampaignAgency] = []
    for chunk in re.split(r"\s*/\s*|\s*,\s*", raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"^(?P<name>.+?)\s*\((?P<country>[^)]+)\)$", chunk)
        if m:
            agencies.append(
                CampaignAgency(
                    name=_clean(m.group("name")),
                    country=country_to_iso(m.group("country")),
                )
            )
        else:
            agencies.append(CampaignAgency(name=_clean(chunk)))
    return agencies


def _parse_entry(
    text: str,
    link: str | None,
    tier: AwardTier,
    category: str,
    year: int,
    source_url: str,
) -> RawCampaign | None:
    m = _ENTRY_RE.match(text)
    if not m:
        return None

    title = _clean(m.group("title"))
    agencies = _parse_agencies(m.group("agencies"))
    rest = m.group("rest")

    # rest = "MARCA de ANUNCIANTE. Prod.: ... País: X."
    # La marca es lo que viene antes del primer " de " o del primer punto.
    first_sentence = rest.split(". ")[0]
    brand_match = re.match(r"^(?P<brand>.+?)\s+de\s+.+$", first_sentence, re.DOTALL)
    brand = _clean(brand_match.group("brand")) if brand_match else _clean(first_sentence)

    country = None
    pais = _PAIS_RE.search(text)
    if pais:
        country = country_to_iso(pais.group("country"))
    if country is None and agencies and agencies[0].country:
        country = agencies[0].country

    links = [CampaignLink(kind=LinkKind.FESTIVAL_PAGE, url=source_url)]
    if link:
        links.insert(0, CampaignLink(kind=LinkKind.CASE_FILM, url=link))

    if not title or not brand:
        return None

    return RawCampaign(
        title=title,
        brand=brand,
        year=year,
        country=country,
        agencies=agencies,
        awards=[
            Award(festival=FESTIVAL_SLUG, year=year, category=category, tier=tier)
        ],
        links=links,
        raw_text=(
            f"Festival: El Ojo de Iberoamérica {year}. "
            f"Premio: {tier.value} en {category}. {_clean(text)}"
        ),
        source_site=SLUG,
        source_url=source_url,
    )


def parse_category_page(html: str, year: int, source_url: str) -> list[RawCampaign]:
    """Parsea una página de categoría (ej: El Ojo Film 2025) a campañas crudas.

    Máquina de estados sobre los <p> del contenido: los <strong> definen el
    nivel del premio vigente, los <em> la subcategoría, y el resto son piezas.
    """
    tree = HTMLParser(html)
    content = tree.css_first("div.entry-content") or tree.css_first("body")
    if content is None:
        return []

    # Nombre de la sección (ej: "El Ojo Film 2025") para dar contexto a la categoría
    h1 = tree.css_first("h1") or tree.css_first("title")
    section = _clean(h1.text()) if h1 else f"El Ojo {year}"
    section = re.sub(r"\s*-\s*El Ojo de Iberoamérica\s*$", "", section)

    campaigns: list[RawCampaign] = []
    tier: AwardTier | None = None
    category = section

    for p in content.css("p"):
        text = _clean(p.text())
        if not text:
            continue

        strong = p.css_first("strong")
        em = p.css_first("em")

        if strong is not None and _tier_from_header(strong.text()) is not None:
            tier = _tier_from_header(strong.text())
            continue

        if em is not None and not text.startswith(("“", '"')):
            # subcategoría: "Alimentos y bebidas – FL1"
            category = f"{section} — {_clean(em.text())}"
            continue

        if text.startswith(("“", '"')) and tier is not None:
            link = _first_external_link(p)
            entry = _parse_entry(text, link, tier, category, year, source_url)
            if entry is not None:
                campaigns.append(entry)

    return campaigns


def _first_external_link(p: Node) -> str | None:
    a = p.css_first("a[href]")
    if a is None:
        return None
    href = a.attributes.get("href", "") or ""
    return href if href.startswith("http") else None


def discover_category_pages(hub_html: str, year: int) -> list[str]:
    """Extrae los links a páginas de categoría desde el hub anual de ganadores."""
    tree = HTMLParser(hub_html)
    seen: set[str] = set()
    urls: list[str] = []
    pattern = re.compile(rf"/premio/finalistas-y?-?ganadores-{year}/[^/]+/?$")
    for a in tree.css("a[href]"):
        href = a.attributes.get("href", "") or ""
        full = urljoin(BASE_URL, href)
        if pattern.search(full) and full not in seen:
            seen.add(full)
            urls.append(full)
    return urls


def hub_url(year: int) -> str:
    # 2017 usa un slug distinto en el sitio
    if year == 2017:
        return f"{BASE_URL}/premio/finalistas-ganadores-{year}/"
    return f"{BASE_URL}/premio/finalistas-y-ganadores-{year}/"


class ElOjoScraper:
    slug = SLUG

    def __init__(self, client=None) -> None:
        from ..http import EthicalClient

        self._client = client or EthicalClient()

    def scrape(
        self,
        year: int | None = None,
        category: str | None = None,
        limit: int | None = None,
    ) -> Iterator[RawCampaign]:
        year = year or 2025
        hub = self._client.get(hub_url(year)).text
        pages = discover_category_pages(hub, year)
        if category:
            pages = [u for u in pages if category.lower() in u.lower()]

        count = 0
        for page_url in pages:
            html = self._client.get(page_url).text
            for campaign in parse_category_page(html, year, page_url):
                yield campaign
                count += 1
                if limit is not None and count >= limit:
                    return
