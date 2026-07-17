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

ENRICH_MODEL = os.environ.get("TRUCHO_ENRICH_MODEL", "claude-sonnet-5")

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
