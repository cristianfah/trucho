"""Embeddings con BAAI/bge-m3 (local, multilingüe ES/PT/EN, 1024 dims).

Dependencia pesada (torch): instalar con `uv sync --extra embed`.
El import es lazy para que el resto del CLI no la necesite.
"""

from functools import lru_cache

from ..config import EMBEDDING_DIMS, EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers no está instalado. "
            "Corré: uv sync --extra embed"
        ) from e
    return SentenceTransformer(EMBEDDING_MODEL)


def embedding_content(summary: str, insight: str, execution: str) -> str:
    """El texto que se embebe: summary + insight + execution."""
    return "\n\n".join(part.strip() for part in (summary, insight, execution) if part)


def embed_text(text: str) -> list[float]:
    vector = _model().encode(text, normalize_embeddings=True)
    result = vector.tolist()
    if len(result) != EMBEDDING_DIMS:
        raise ValueError(f"Se esperaban {EMBEDDING_DIMS} dims, llegaron {len(result)}")
    return result
