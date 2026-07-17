"""Configuración del pipeline: todo secreto vive en .env (nunca commiteado)."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Busca el .env en la raíz del monorepo (dos niveles arriba de apps/ingestion)
# y también en el cwd, para que `uv run trucho` funcione desde cualquier lado.
_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()  # .env del cwd, si existe

USER_AGENT = os.environ.get(
    "TRUCHO_USER_AGENT",
    "trucho-bot/0.1 (+https://github.com/cristianfah/trucho)",
)

# Rate limiting: 1 request cada 2 segundos por dominio (scraping ético)
RATE_LIMIT_SECONDS = 2.0

# Proveedor de enrichment: "anthropic" (default) u "openrouter" (API
# OpenAI-compatible, para correr modelos alternativos sobre el mismo prompt).
ENRICHMENT_PROVIDERS = ("anthropic", "openrouter")
ENRICHMENT_PROVIDER = os.environ.get("ENRICHMENT_PROVIDER", "anthropic").strip().lower()

DEFAULT_ENRICH_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openrouter": "deepseek/deepseek-chat",
}

# ENRICHMENT_MODEL es el nombre nuevo; TRUCHO_ENRICH_MODEL se acepta por
# retrocompatibilidad.
ENRICH_MODEL = (
    os.environ.get("ENRICHMENT_MODEL")
    or os.environ.get("TRUCHO_ENRICH_MODEL")
    or DEFAULT_ENRICH_MODELS.get(ENRICHMENT_PROVIDER, "claude-sonnet-5")
)


def resolve_provider_model(model: str | None = None) -> tuple[str, str]:
    """Resuelve (provider, model) para el enrichment.

    Con `model` explícito (flag --model) el provider se infiere del formato:
    los ids de OpenRouter siempre llevan "/" (vendor/model), los de Anthropic no.
    Sin flag, manda ENRICHMENT_PROVIDER + ENRICHMENT_MODEL del .env.
    """
    if model:
        return ("openrouter" if "/" in model else "anthropic"), model
    if ENRICHMENT_PROVIDER not in ENRICHMENT_PROVIDERS:
        raise RuntimeError(
            f"ENRICHMENT_PROVIDER inválido: '{ENRICHMENT_PROVIDER}'. "
            f"Valores posibles: {', '.join(ENRICHMENT_PROVIDERS)}."
        )
    return ENRICHMENT_PROVIDER, ENRICH_MODEL

EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIMS = 1024

MIGRATIONS_DIR = _REPO_ROOT / "packages" / "db" / "migrations"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL no está definida. Copiá .env.example a .env y completala."
        )
    return url


def anthropic_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY no está definida. El paso de enrichment la necesita."
        )
    return key


def openrouter_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY no está definida. El enrichment vía OpenRouter la necesita."
        )
    return key
