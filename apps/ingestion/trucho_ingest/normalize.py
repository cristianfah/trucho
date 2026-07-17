"""Normalización: slugs, países, y matching fuzzy para dedupe."""

import re
import unicodedata

from rapidfuzz import fuzz

# Nombres de país en español (como aparecen en las fuentes iberoamericanas)
# → ISO 3166-1 alpha-2.
COUNTRY_ES_TO_ISO = {
    "argentina": "AR",
    "bolivia": "BO",
    "brasil": "BR",
    "chile": "CL",
    "colombia": "CO",
    "costa rica": "CR",
    "cuba": "CU",
    "ecuador": "EC",
    "el salvador": "SV",
    "españa": "ES",
    "estados unidos": "US",
    "guatemala": "GT",
    "honduras": "HN",
    "mexico": "MX",
    "méxico": "MX",
    "nicaragua": "NI",
    "panama": "PA",
    "panamá": "PA",
    "paraguay": "PY",
    "peru": "PE",
    "perú": "PE",
    "portugal": "PT",
    "puerto rico": "PR",
    "republica dominicana": "DO",
    "república dominicana": "DO",
    "uruguay": "UY",
    "venezuela": "VE",
    "reino unido": "GB",
    "francia": "FR",
    "alemania": "DE",
    "italia": "IT",
}

# Nombres de país en inglés (como aparecen en LTWM y el dataset de
# Internet Archive) → ISO 3166-1 alpha-2.
COUNTRY_EN_TO_ISO = {
    "argentina": "AR",
    "australia": "AU",
    "austria": "AT",
    "belgium": "BE",
    "bolivia": "BO",
    "brazil": "BR",
    "canada": "CA",
    "chile": "CL",
    "china": "CN",
    "colombia": "CO",
    "costa rica": "CR",
    "cuba": "CU",
    "czech republic": "CZ",
    "czechoslovakia": "CZ",
    "denmark": "DK",
    "ecuador": "EC",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "west germany": "DE",
    "greece": "GR",
    "guatemala": "GT",
    "hong kong": "HK",
    "hungary": "HU",
    "india": "IN",
    "ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "japan": "JP",
    "lebanon": "LB",
    "mexico": "MX",
    "netherlands": "NL",
    "the netherlands": "NL",
    "new zealand": "NZ",
    "norway": "NO",
    "panama": "PA",
    "paraguay": "PY",
    "peru": "PE",
    "poland": "PL",
    "portugal": "PT",
    "puerto rico": "PR",
    "russia": "RU",
    "singapore": "SG",
    "south africa": "ZA",
    "south korea": "KR",
    "soviet union": "RU",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "thailand": "TH",
    "turkey": "TR",
    "united arab emirates": "AE",
    "united kingdom": "GB",
    "great britain": "GB",
    "england": "GB",
    "united states": "US",
    "usa": "US",
    "uruguay": "UY",
    "venezuela": "VE",
    "yugoslavia": "RS",
}


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def slugify(text: str, max_length: int = 80) -> str:
    text = strip_accents(text.lower())
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_length].rstrip("-")


def campaign_slug(brand: str, title: str, year: int | None) -> str:
    parts = [slugify(brand, 30), slugify(title, 60)]
    if year:
        parts.append(str(year))
    return "-".join(p for p in parts if p)


def country_to_iso(name: str | None) -> str | None:
    """Convierte un nombre de país (español o inglés) a ISO 3166-1 alpha-2."""
    if not name:
        return None
    key = strip_accents(name.strip().lower().rstrip("."))
    # probar con y sin tildes, en ambos idiomas
    for candidate in (name.strip().lower().rstrip("."), key):
        if candidate in COUNTRY_ES_TO_ISO:
            return COUNTRY_ES_TO_ISO[candidate]
        if candidate in COUNTRY_EN_TO_ISO:
            return COUNTRY_EN_TO_ISO[candidate]
    return None


def normalized_key(brand: str, title: str) -> str:
    """Clave normalizada para matching de duplicados."""
    return f"{slugify(brand)}::{slugify(title)}"


def _norm_text(text: str) -> str:
    return slugify(text).replace("-", " ")


def is_same_campaign(
    brand_a: str, title_a: str, year_a: int | None,
    brand_b: str, title_b: str, year_b: int | None,
) -> bool:
    """Fuzzy matching por (brand + título normalizado + año).

    La misma campaña aparece en múltiples fuentes con variaciones de escritura:
    mayúsculas ("THE WHOPPER DETOUR" vs "The Whopper Detour"), artículos
    ("Whopper Detour"), marcas con alias ("Axe/Lynx" vs "AXE"). Los años
    pueden diferir en 1 (inscripción vs premiación en festivales distintos).
    """
    if year_a is not None and year_b is not None and abs(year_a - year_b) > 1:
        return False

    ta, tb = _norm_text(title_a), _norm_text(title_b)
    ba, bb = _norm_text(brand_a), _norm_text(brand_b)
    if not (ta and tb and ba and bb):
        return False

    # Título: token_set tolera artículos/orden, ratio evita matches por
    # subconjunto de palabras demasiado laxos.
    title_ok = fuzz.token_set_ratio(ta, tb) >= 95 and fuzz.ratio(ta, tb) >= 75
    # Marca: alcanza con que una escritura contenga a la otra (Axe vs Axe/Lynx).
    brand_ok = fuzz.token_set_ratio(ba, bb) >= 90 or fuzz.ratio(ba, bb) >= 90
    return title_ok and brand_ok
