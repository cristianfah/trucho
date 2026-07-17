"""Batch API de Anthropic para corridas masivas de enrichment (50% descuento).

Flujo: submit_batch envía todas las campañas pendientes en un solo batch,
wait_for_batch hace polling hasta que termina, e iter_batch_results devuelve
los resultados. La validación Pydantic y el fallback (reintento sincrónico de
lo que no pasó el schema) los maneja el CLI.
"""

import time
from collections.abc import Callable, Iterator

import anthropic

from ..config import anthropic_api_key
from .analyze import _TOOL, _format_prompt
from .prompt import SYSTEM_PROMPT

POLL_SECONDS = 30


def make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=anthropic_api_key())


def submit_batch(
    campaigns: list[dict], model: str, client: anthropic.Anthropic | None = None
) -> str:
    """Envía un batch con una request por campaña; custom_id = campaign id."""
    client = client or make_client()
    requests = [
        {
            "custom_id": str(c["id"]),
            "params": {
                "model": model,
                "max_tokens": 2048,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": _format_prompt(c)}],
                "tools": [_TOOL],
                "tool_choice": {"type": "tool", "name": "guardar_analisis"},
            },
        }
        for c in campaigns
    ]
    batch = client.messages.batches.create(requests=requests)
    return batch.id


def wait_for_batch(
    batch_id: str,
    client: anthropic.Anthropic | None = None,
    poll_seconds: float = POLL_SECONDS,
    on_poll: Callable | None = None,
):
    """Bloquea hasta que el batch termina de procesar. Devuelve el batch final."""
    client = client or make_client()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if on_poll:
            on_poll(batch)
        if batch.processing_status == "ended":
            return batch
        time.sleep(poll_seconds)


def iter_batch_results(
    batch_id: str, client: anthropic.Anthropic | None = None
) -> Iterator[tuple[str, object]]:
    """Itera (custom_id, result) de un batch terminado.

    result.type es succeeded | errored | canceled | expired; si succeeded,
    result.message trae la respuesta normal (con el bloque tool_use).
    """
    client = client or make_client()
    for entry in client.messages.batches.results(batch_id):
        yield entry.custom_id, entry.result
