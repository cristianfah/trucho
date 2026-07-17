"""Interfaz común de los scrapers: cada fuente implementa `scrape()`."""

from collections.abc import Iterator
from typing import Protocol

from ..models import RawCampaign


class Scraper(Protocol):
    """Un scraper por fuente. Emite campañas crudas (solo hechos, sin análisis)."""

    slug: str  # identificador de la fuente: elojo, ltw, fiap...

    def scrape(
        self,
        year: int | None = None,
        category: str | None = None,
        limit: int | None = None,
    ) -> Iterator[RawCampaign]: ...
