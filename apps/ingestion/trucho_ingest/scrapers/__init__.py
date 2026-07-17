"""Registro de scrapers: uno por fuente."""

from .elojo import ElOjoScraper

SCRAPERS = {
    ElOjoScraper.slug: ElOjoScraper,
}


def get_scraper(slug: str):
    if slug not in SCRAPERS:
        available = ", ".join(sorted(SCRAPERS))
        raise KeyError(f"No existe el scraper '{slug}'. Disponibles: {available}")
    return SCRAPERS[slug]()
