"""Tests del flujo de enrichment con un cliente Anthropic falso (sin red)."""

from types import SimpleNamespace

import pytest

from trucho_ingest.enrichment.analyze import (
    EnrichmentError,
    analyze_campaign,
)

CAMPAIGN = {
    "title": "Sweeter than the sweetest",
    "brand": "Axe/Lynx",
    "year": 2025,
    "country": "ES",
    "agencies": [{"name": "LOLA MullenLowe"}],
    "awards": [
        {"festival": "el-ojo", "year": 2025, "category": "Film", "tier": "grand_prix"}
    ],
    "raw_text": "Festival: El Ojo 2025...",
}

VALID_ANALYSIS = {
    "summary": "Un resumen.",
    "description": "Una descripción completa de la campaña.",
    "insight": "Un insight humano.",
    "execution": "Cine y TV, case film.",
    "results": None,
    "industry": "fmcg",
    "tags": ["humor", "marca-de-desodorante"],
    "language": "en",
}


class FakeClient:
    """Devuelve una secuencia de respuestas tool_use predefinidas."""

    def __init__(self, inputs: list[dict]):
        self._inputs = list(inputs)
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        block = SimpleNamespace(
            type="tool_use", id=f"tu_{self.calls}", input=self._inputs.pop(0)
        )
        return SimpleNamespace(content=[block])


def test_valid_analysis_parses():
    client = FakeClient([VALID_ANALYSIS])
    analysis = analyze_campaign(CAMPAIGN, client=client)
    assert analysis.summary == "Un resumen."
    assert analysis.industry.value == "fmcg"
    assert analysis.results is None
    assert client.calls == 1


def test_invalid_analysis_retries_once_then_succeeds():
    broken = dict(VALID_ANALYSIS, tags=[])  # tags exige min_length=1
    client = FakeClient([broken, VALID_ANALYSIS])
    analysis = analyze_campaign(CAMPAIGN, client=client)
    assert client.calls == 2
    assert analysis.tags == ["humor", "marca-de-desodorante"]


def test_invalid_analysis_twice_raises():
    broken = dict(VALID_ANALYSIS, industry="no-existe")
    client = FakeClient([broken, broken])
    with pytest.raises(EnrichmentError):
        analyze_campaign(CAMPAIGN, client=client)
