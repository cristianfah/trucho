"""Cliente OpenRouter para el enrichment (API OpenAI-compatible).

Usa el mismo prompt y el mismo schema Pydantic que el camino Anthropic, pero
vía function calling estilo OpenAI. Los modelos baratos fallan el schema más
seguido, así que acá los intentos suben a 3 (vs 2 en anthropic), siempre
devolviéndole el error de validación al modelo como feedback.
"""

import json

import httpx
from pydantic import ValidationError

from ..config import USER_AGENT, openrouter_api_key
from ..models import CampaignAnalysis
from .prompt import SYSTEM_PROMPT

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MAX_ATTEMPTS = 3

_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "guardar_analisis",
        "description": "Guarda el análisis estructurado de la campaña en la base de datos.",
        "parameters": CampaignAnalysis.model_json_schema(),
    },
}


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    """Cliente mínimo sobre httpx; `transport` inyectable para tests."""

    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 180.0,
    ):
        self._http = httpx.Client(
            base_url=OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key or openrouter_api_key()}",
                "HTTP-Referer": "https://github.com/cristianfah/trucho",
                "X-Title": "trucho",
                "User-Agent": USER_AGENT,
            },
            timeout=timeout,
            transport=transport,
        )

    def chat(self, payload: dict) -> dict:
        response = self._http.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        # OpenRouter puede devolver 200 con un objeto de error adentro
        if isinstance(data, dict) and data.get("error"):
            raise OpenRouterError(str(data["error"]))
        return data


def analyze_campaign_openrouter(
    campaign: dict, model: str, client: OpenRouterClient | None = None
) -> CampaignAnalysis:
    from .analyze import EnrichmentError, _format_prompt

    client = client or OpenRouterClient()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _format_prompt(campaign)},
    ]

    last_error: Exception | str | None = None
    for _attempt in range(OPENROUTER_MAX_ATTEMPTS):
        data = client.chat(
            {
                "model": model,
                "max_tokens": 2048,
                "messages": messages,
                "tools": [_TOOL_OPENAI],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": "guardar_analisis"},
                },
            }
        )
        message = data["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            last_error = "el modelo no llamó a la herramienta guardar_analisis"
            messages = messages + [
                {"role": "assistant", "content": message.get("content") or ""},
                {
                    "role": "user",
                    "content": "Tenés que responder llamando a la herramienta "
                    "`guardar_analisis` con el análisis estructurado. Reintentá.",
                },
            ]
            continue

        tool_call = tool_calls[0]
        try:
            args = json.loads(tool_call["function"]["arguments"])
        except (json.JSONDecodeError, TypeError) as e:
            last_error = e
            feedback = f"Los argumentos no eran JSON válido ({e}). Corregí y reintentá."
        else:
            try:
                return CampaignAnalysis.model_validate(args)
            except ValidationError as e:
                last_error = e
                feedback = f"Validación fallida, corregí y reintentá: {e}"

        # reintento con el error como feedback, formato OpenAI (rol tool)
        messages = messages + [
            {
                "role": "assistant",
                "content": message.get("content") or None,
                "tool_calls": tool_calls,
            },
            {
                "role": "tool",
                "tool_call_id": tool_call.get("id") or "call_0",
                "content": feedback,
            },
        ]

    raise EnrichmentError(
        f"El análisis de '{campaign['title']}' no pasó la validación "
        f"({model} vía openrouter): {last_error}"
    )
