"""Tests del cliente OpenRouter con transporte httpx mockeado (sin red)."""

import json

import httpx
import pytest

from trucho_ingest.config import resolve_provider_model
from trucho_ingest.enrichment.analyze import EnrichmentError
from trucho_ingest.enrichment.openrouter import (
    OPENROUTER_MAX_ATTEMPTS,
    OpenRouterClient,
    OpenRouterError,
    analyze_campaign_openrouter,
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


def _tool_response(arguments: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "guardar_analisis",
                                "arguments": arguments,
                            },
                        }
                    ],
                }
            }
        ]
    }


def _make_client(responses: list[dict]) -> tuple[OpenRouterClient, list[dict]]:
    """Cliente con MockTransport que sirve `responses` en orden y captura
    los payloads enviados."""
    responses = list(responses)
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=responses.pop(0))

    client = OpenRouterClient(api_key="test-key", transport=httpx.MockTransport(handler))
    return client, requests


def test_valid_analysis_parses_and_forces_tool():
    client, requests = _make_client([_tool_response(json.dumps(VALID_ANALYSIS))])
    analysis = analyze_campaign_openrouter(CAMPAIGN, model="deepseek/deepseek-chat", client=client)
    assert analysis.summary == "Un resumen."
    assert analysis.industry.value == "fmcg"
    assert len(requests) == 1
    payload = requests[0]
    assert payload["model"] == "deepseek/deepseek-chat"
    assert payload["tool_choice"]["function"]["name"] == "guardar_analisis"
    assert payload["messages"][0]["role"] == "system"


def test_invalid_analysis_retries_with_tool_feedback():
    broken = dict(VALID_ANALYSIS, tags=[])  # tags exige min_length=1
    client, requests = _make_client(
        [
            _tool_response(json.dumps(broken)),
            _tool_response(json.dumps(VALID_ANALYSIS)),
        ]
    )
    analysis = analyze_campaign_openrouter(CAMPAIGN, model="deepseek/deepseek-chat", client=client)
    assert analysis.tags == ["humor", "marca-de-desodorante"]
    assert len(requests) == 2
    # el segundo request lleva el error como mensaje rol tool
    retry_messages = requests[1]["messages"]
    assert retry_messages[-1]["role"] == "tool"
    assert "Validación fallida" in retry_messages[-1]["content"]


def test_malformed_json_arguments_retries():
    client, requests = _make_client(
        [
            _tool_response("{esto no es json"),
            _tool_response(json.dumps(VALID_ANALYSIS)),
        ]
    )
    analysis = analyze_campaign_openrouter(CAMPAIGN, model="deepseek/deepseek-chat", client=client)
    assert analysis.summary == "Un resumen."
    assert len(requests) == 2


def test_missing_tool_call_retries():
    no_tool = {"choices": [{"message": {"role": "assistant", "content": "bla"}}]}
    client, requests = _make_client(
        [no_tool, _tool_response(json.dumps(VALID_ANALYSIS))]
    )
    analysis = analyze_campaign_openrouter(CAMPAIGN, model="deepseek/deepseek-chat", client=client)
    assert analysis.summary == "Un resumen."
    assert len(requests) == 2


def test_three_invalid_attempts_raise():
    broken = dict(VALID_ANALYSIS, industry="no-existe")
    client, requests = _make_client(
        [_tool_response(json.dumps(broken))] * OPENROUTER_MAX_ATTEMPTS
    )
    with pytest.raises(EnrichmentError):
        analyze_campaign_openrouter(CAMPAIGN, model="deepseek/deepseek-chat", client=client)
    assert len(requests) == OPENROUTER_MAX_ATTEMPTS


def test_api_error_in_200_body_raises():
    client, _ = _make_client([{"error": {"message": "rate limited", "code": 429}}])
    with pytest.raises(OpenRouterError):
        analyze_campaign_openrouter(CAMPAIGN, model="deepseek/deepseek-chat", client=client)


def test_resolve_provider_model_infers_from_slash():
    assert resolve_provider_model("deepseek/deepseek-chat") == (
        "openrouter",
        "deepseek/deepseek-chat",
    )
    assert resolve_provider_model("claude-sonnet-4-6") == (
        "anthropic",
        "claude-sonnet-4-6",
    )
