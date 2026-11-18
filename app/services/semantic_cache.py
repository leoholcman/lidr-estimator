"""Caché semántica en memoria.

Dos peticiones se consideran la misma si:
1. Coincide el *bucket* (versión de prompt, tipo, detalle, formato, tier y
   tamaño de adjuntos). Con opciones distintas el prompt es distinto, así que
   nunca comparten entrada aunque el texto se parezca.
2. La similitud coseno entre los embeddings de sus textos es >= threshold.

Solo se usa en el primer turno de una sesión: con historial, que el mensaje se
parezca a otro no implica que la respuesta sirva.

En clase se hizo con Redis Stack; acá es una lista en memoria para no sumar
infraestructura. La interfaz (lookup/store) es la misma.
"""

import math
from collections.abc import Awaitable, Callable
from dataclasses import replace

import structlog
from openai import AsyncOpenAI

from app.config import settings
from app.services.providers import LLMResult

logger = structlog.get_logger()

Embedder = Callable[[str], Awaitable[list[float]]]
MAX_EMBED_CHARS = 8000  # el modelo de embeddings admite ~8k tokens


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class SemanticCache:
    def __init__(self, embedder: Embedder, threshold: float = 0.92, max_entries: int = 500):
        self.embedder = embedder
        self.threshold = threshold
        self.max_entries = max_entries
        self._entries: list[tuple[str, list[float], LLMResult]] = []

    async def lookup(self, bucket: str, text: str) -> tuple[LLMResult | None, list[float]]:
        """Devuelve `(resultado o None, embedding)`; el embedding se reutiliza en `store`."""
        vector = await self.embedder(text[:MAX_EMBED_CHARS])
        best, best_score = None, 0.0
        for entry_bucket, entry_vector, result in self._entries:
            if entry_bucket != bucket:
                continue
            score = cosine(vector, entry_vector)
            if score > best_score:
                best, best_score = result, score
        hit = best is not None and best_score >= self.threshold
        logger.info("semantic_cache.lookup", bucket=bucket, score=round(best_score, 4), hit=hit)
        return (replace(best, cache_hit=True) if hit else None), vector

    def store(self, bucket: str, vector: list[float], result: LLMResult) -> None:
        if len(self._entries) >= self.max_entries:
            self._entries.pop(0)
        self._entries.append((bucket, vector, result))

    def clear(self) -> None:
        self._entries.clear()


async def _openai_embedder(text: str) -> list[float]:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.embeddings.create(model=settings.embedding_model, input=text)
    return response.data[0].embedding


def build_semantic_cache() -> SemanticCache | None:
    """None si está desactivada o no hay clave de OpenAI para los embeddings."""
    if not settings.semantic_cache_enabled or not settings.openai_api_key:
        return None
    return SemanticCache(_openai_embedder, threshold=settings.semantic_cache_threshold)
