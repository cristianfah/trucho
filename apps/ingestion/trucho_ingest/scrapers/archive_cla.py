"""Importer del dataset "Cannes Lions Film Winners 1954-2000" de Internet Archive.

https://archive.org/details/cannes-lions-advertising-film-winners

Es el registro consolidado más completo de ganadores de Film de Cannes de ese
período publicado en internet abierto: un Excel con una hoja por año y columnas
Award / Category / Brand / Product / Title / Agency / City / Production / City /
Country / Source / Comments (algunos años agregan "Entrant"; se parsea por
nombre de header, no por posición).

Advertencias del propio dataset (ver docs/sources/archive-org-cla.md):
- Error de fechas conocido que se propaga en los ganadores de 1999-2000
  → esas filas se cargan con confidence='low'.
- Registro incompleto por naturaleza; entradas entre paréntesis o con "?"
  indican incertidumbre → también confidence='low'.
"""

import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

from ..models import (
    Award,
    AwardTier,
    CampaignAgency,
    CampaignLink,
    LinkKind,
    RawCampaign,
    SourceConfidence,
)
from ..normalize import country_to_iso

SLUG = "archive-org-cla"
FESTIVAL_SLUG = "cannes"
ITEM_URL = "https://archive.org/details/cannes-lions-advertising-film-winners"
XLSX_URL = (
    "https://archive.org/download/cannes-lions-advertising-film-winners/"
    "Cannes%20Lions%20Film%201954-2000.xlsx"
)

# Años con el error de fechas conocido del dataset
LOW_CONFIDENCE_YEARS = {1999, 2000}

# Premios que no corresponden a una pieza (premios a agencias/personas/reels)
_SKIP_AWARDS = {
    "agency of the year",
    "journalists",
    "palme d'or",
    "palme d’or",
}

_TIER_RULES: list[tuple[re.Pattern, AwardTier]] = [
    (re.compile(r"grand prix", re.I), AwardTier.GRAND_PRIX),
    (re.compile(r"^gold", re.I), AwardTier.GOLD),
    (re.compile(r"^(1st|1)$", re.I), AwardTier.GOLD),
    (re.compile(r"^s.lver", re.I), AwardTier.SILVER),  # tolera el typo "SIlver"
    (re.compile(r"^(2nd|2|runner.?up)$", re.I), AwardTier.SILVER),
    (re.compile(r"^bronze", re.I), AwardTier.BRONZE),
    (re.compile(r"^(3rd|3)$", re.I), AwardTier.BRONZE),
    (re.compile(r"^(short ?list|diploma|mention|honou?rable mention)", re.I),
     AwardTier.SHORTLIST),
    (re.compile(r"^(\d+|\d+th)$", re.I), AwardTier.SHORTLIST),
]


def tier_from_award(award: str) -> AwardTier:
    text = award.strip()
    for pattern, tier in _TIER_RULES:
        if pattern.search(text):
            return tier
    return AwardTier.WINNER


def _cell(row: dict, key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _row_confidence(year: int, award: str) -> SourceConfidence:
    if year in LOW_CONFIDENCE_YEARS:
        return SourceConfidence.LOW
    if "?" in award or "disputed" in award.lower():
        return SourceConfidence.LOW
    return SourceConfidence.NORMAL


def _header_map(header: tuple) -> dict[int, str]:
    """Mapea índice de columna → nombre, desambiguando las dos "City"
    (la primera es de la agencia, la segunda de la productora)."""
    result: dict[int, str] = {}
    seen_city = 0
    for i, name in enumerate(header):
        if name is None:
            continue
        name = str(name).strip()
        if name.lower() == "city":
            seen_city += 1
            name = "AgencyCity" if seen_city == 1 else "ProductionCity"
        result[i] = name
    return result


def parse_workbook(xlsx_path: Path, year_filter: int | None = None) -> Iterator[RawCampaign]:
    """Parsea el Excel del dataset a campañas crudas. Testeable sin red."""
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    for sheet_name in wb.sheetnames:
        if not re.fullmatch(r"(19|20)\d\d", sheet_name.strip()):
            continue  # "Indeterminate Year", "Unconfirmed", "1958 (Collection...)"
        year = int(sheet_name.strip())
        if year_filter is not None and year != year_filter:
            continue

        ws = wb[sheet_name]
        headers: dict[int, str] | None = None
        last_award: str | None = None
        for values in ws.iter_rows(values_only=True):
            if headers is None:
                headers = _header_map(values)
                continue
            if not any(values):
                continue
            row = {headers[i]: v for i, v in enumerate(values) if i in headers}

            # un Award vacío hereda el de la fila anterior (formato del Excel)
            award = _cell(row, "Award") or last_award
            if award is None:
                continue
            last_award = award
            if award.strip().lower() in _SKIP_AWARDS:
                continue

            title = _cell(row, "Title")
            brand = _cell(row, "Brand")
            product = _cell(row, "Product")
            if brand is None:
                brand = product
            if title is None:
                title = product or brand
            if not title or not brand:
                continue  # premios sin pieza identificable (reels, personas)

            campaign = _build_campaign(row, year, award, title, brand)
            if campaign is not None:
                yield campaign

        del last_award


def _build_campaign(
    row: dict, year: int, award: str, title: str, brand: str
) -> RawCampaign | None:
    category = _cell(row, "Category")
    agency = _cell(row, "Agency")
    agency_city = _cell(row, "AgencyCity")
    production = _cell(row, "Production")
    country_name = _cell(row, "Country")
    source_ids = _cell(row, "Source")
    comments = _cell(row, "Comments")
    product = _cell(row, "Product")

    agencies = []
    if agency:
        agencies.append(CampaignAgency(name=agency))
    if production:
        from ..models import AgencyRole

        agencies.append(CampaignAgency(name=production, role=AgencyRole.PROD))

    parts = [f"Festival: Cannes Lions {year} (Film). Premio: {award}"]
    if category:
        parts.append(f"en la categoría {category}")
    parts.append(f". Pieza: {title}. Marca: {brand}.")
    if product:
        parts.append(f"Producto: {product}.")
    if agency:
        parts.append(f"Agencia: {agency}{f' ({agency_city})' if agency_city else ''}.")
    if production:
        parts.append(f"Productora: {production}.")
    if country_name:
        parts.append(f"País: {country_name}.")
    if comments:
        parts.append(f"Notas del registro: {comments}.")
    if source_ids:
        parts.append(f"IDs de fuente del dataset: {source_ids}.")

    return RawCampaign(
        title=title,
        brand=brand,
        year=year,
        country=country_to_iso(country_name),
        agencies=agencies,
        awards=[
            Award(
                festival=FESTIVAL_SLUG,
                year=year,
                category=f"Film — {category}" if category else "Film",
                tier=tier_from_award(award),
            )
        ],
        links=[CampaignLink(kind=LinkKind.FESTIVAL_PAGE, url=ITEM_URL)],
        raw_text=" ".join(parts),
        source_site=SLUG,
        source_url=ITEM_URL,
        confidence=_row_confidence(year, award),
    )


class ArchiveClaImporter:
    slug = SLUG

    def __init__(self, client=None, cache_dir: Path | None = None) -> None:
        from ..http import EthicalClient

        self._client = client or EthicalClient()
        self._cache_dir = cache_dir or Path(tempfile.gettempdir()) / "trucho-cache"

    def _download(self) -> Path:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        target = self._cache_dir / "cannes-lions-film-1954-2000.xlsx"
        if not target.exists():
            resp = self._client.get(XLSX_URL)
            target.write_bytes(resp.content)
        return target

    def scrape(
        self,
        year: int | None = None,
        category: str | None = None,
        limit: int | None = None,
    ) -> Iterator[RawCampaign]:
        xlsx = self._download()
        count = 0
        for campaign in parse_workbook(xlsx, year_filter=year):
            if category and not any(
                category.lower() in (a.category or "").lower() for a in campaign.awards
            ):
                continue
            yield campaign
            count += 1
            if limit is not None and count >= limit:
                return
