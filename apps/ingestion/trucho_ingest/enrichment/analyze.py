"""Enrichment: un LLM recibe el texto crudo y genera el análisis estructurado.

Proveedores:
- anthropic (default): tool-use forzado con el JSON Schema del modelo Pydantic.
- openrouter: API OpenAI-compatible (function calling) para correr modelos
  alternativos (deepseek, gemini...) sobre el mismo prompt. Ver openrouter.py.

En ambos casos el output llega validado por Pydantic, con reintentos que le
devuelven el error de validación al modelo como feedback (2 intentos con
anthropic, 3 con openrouter — los modelos baratos fallan el schema más seguido).
"""

import anthropic
from pydantic import ValidationError

from ..config import resolve_provider_model
from ..models import CampaignAnalysis
from .prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

_TOOL = {
    "name": "guardar_analisis",
    "description": "Guarda el análisis estructurado de la campaña en la base de datos.",
    "input_schema": CampaignAnalysis.model_json_schema(),
}

ANTHROPIC_MAX_ATTEMPTS = 2


class EnrichmentError(RuntimeError):
    pass


def _format_prompt(campaign: dict) -> str:
    awards = "; ".join(
        f"{a['tier']} — {a['category'] or 'sin categoría'} ({a['festival']} {a['year']})"
        for a in campaign.get("awards", [])
    ) or "desconocidos"
    agencies = ", ".join(a["name"] for a in campaign.get("agencies", [])) or "desconocida"
    return USER_PROMPT_TEMPLATE.format(
        title=campaign["title"],
        brand=campaign["brand"],
        year=campaign.get("year") or "desconocido",
        country=campaign.get("country") or "desconocido",
        agencies=agencies,
        awards=awards,
        raw_text=campaign.get("raw_text") or "(sin texto adicional)",
    )


def analyze_campaign(
    campaign: dict,
    client=None,
    provider: str | None = None,
    model: str | None = None,
) -> CampaignAnalysis:
    """Genera el análisis de una campaña. `campaign` es un dict con los campos
    crudos (title, brand, year, country, agencies, awards, raw_text).

    `provider`/`model` se resuelven desde el .env si no vienen explícitos.
    """
    if provider is None:
        provider, resolved_model = resolve_provider_model(model)
        model = resolved_model
    elif model is None:
        _, model = resolve_provider_model(None)

    if provider == "openrouter":
        from .openrouter import analyze_campaign_openrouter

        return analyze_campaign_openrouter(campaign, model=model, client=client)

    return _analyze_anthropic(campaign, model=model, client=client)


def _analyze_anthropic(
    campaign: dict, model: str, client: anthropic.Anthropic | None = None
) -> CampaignAnalysis:
    from ..config import anthropic_api_key

    client = client or anthropic.Anthropic(api_key=anthropic_api_key())
    messages = [{"role": "user", "content": _format_prompt(campaign)}]

    last_error: Exception | None = None
    for _attempt in range(ANTHROPIC_MAX_ATTEMPTS):
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "guardar_analisis"},
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        try:
            return CampaignAnalysis.model_validate(tool_use.input)
        except ValidationError as e:
            last_error = e
            # reintento con el error como feedback
            messages = messages + [
                {"role": "assistant", "content": response.content},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": f"Validación fallida, corregí y reintentá: {e}",
                            "is_error": True,
                        }
                    ],
                },
            ]

    raise EnrichmentError(
        f"El análisis de '{campaign['title']}' no pasó la validación: {last_error}"
    )
