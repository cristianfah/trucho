"""Registro de scrapers: uno por fuente."""

from .archive_cla import ArchiveClaImporter
from .elojo import ElOjoScraper
from .ltwm import LtwmScraper

SCRAPERS = {
    ElOjoScraper.slug: ElOjoScraper,
    LtwmScraper.slug: LtwmScraper,
    ArchiveClaImporter.slug: ArchiveClaImporter,
}


def get_scraper(slug: str):
    if slug not in SCRAPERS:
        available = ", ".join(sorted(SCRAPERS))
        raise KeyError(f"No existe el scraper '{slug}'. Disponibles: {available}")
    return SCRAPERS[slug]()
