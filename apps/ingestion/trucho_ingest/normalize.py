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
    """Convierte un nombre de país en español a ISO 3166-1 alpha-2."""
    if not name:
        return None
    key = strip_accents(name.strip().lower().rstrip("."))
    # probar con y sin tildes
    for candidate in (name.strip().lower().rstrip("."), key):
        if candidate in COUNTRY_ES_TO_ISO:
            return COUNTRY_ES_TO_ISO[candidate]
    return None


def normalized_key(brand: str, title: str) -> str:
    """Clave normalizada para matching de duplicados."""
    return f"{slugify(brand)}::{slugify(title)}"


def is_same_campaign(
    brand_a: str, title_a: str, year_a: int | None,
    brand_b: str, title_b: str, year_b: int | None,
    threshold: int = 90,
) -> bool:
    """Fuzzy matching por (brand + título normalizado + año).

    La misma campaña puede aparecer en múltiples fuentes con variaciones
    menores de escritura; años pueden diferir en 1 (inscripción vs premiación).
    """
    if year_a is not None and year_b is not None and abs(year_a - year_b) > 1:
        return False
    brand_score = fuzz.ratio(slugify(brand_a), slugify(brand_b))
    title_score = fuzz.ratio(slugify(title_a), slugify(title_b))
    return brand_score >= threshold and title_score >= threshold
