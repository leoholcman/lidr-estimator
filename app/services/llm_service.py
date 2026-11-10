"""Lógica de llamada al LLM.

CAG: los ejemplos de estimaciones previas viajan en el system prompt de cada
llamada (ver app/prompts). No hay retrieval: todo el contexto está precargado.
"""

import time
from collections.abc import AsyncIterator

import structlog

from app.config import settings
from app.prompts.loader import DEFAULT_VERSION, render_estimation_prompt
from app.schemas import EstimationRequest
from app.services.cache import ResponseCache
from app.services.providers import (
    PROVIDER_ERRORS,
    LLMError,
    LLMProvider,
    LLMResult,
    Message,
    StreamEvent,
    get_provider,
)

logger = structlog.get_logger()

_provider: LLMProvider | None = None
cache = ResponseCache(ttl_seconds=settings.cache_ttl_seconds)


def provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = get_provider(settings)
    return _provider


def _log_call(result: LLMResult, started: float, stream: bool) -> None:
    logger.info(
        "llm.call",
        provider=result.provider,
        model=result.model,
        stream=stream,
        cache_hit=result.cache_hit,
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


async def complete(system: str, messages: list[Message]) -> LLMResult:
    """Llamada completa (sin streaming), con caché exact-match."""
    started = time.perf_counter()
    llm = provider()
    key = cache.key(llm.model, system, messages)
    if (cached := cache.get(key)) is not None:
        _log_call(cached, started, stream=False)
        return cached
    try:
        result = await llm.complete(system, messages)
    except PROVIDER_ERRORS as e:
        logger.exception("llm.error", provider=llm.name)
        raise LLMError(f"Error del proveedor LLM: {e}") from e
    cache.set(key, result)
    _log_call(result, started, stream=False)
    return result


async def stream(system: str, messages: list[Message]) -> AsyncIterator[StreamEvent]:
    """Igual que `complete` pero emite el texto a medida que llega.

    Si la respuesta está en caché, se emite entera de una vez.
    """
    started = time.perf_counter()
    llm = provider()
    key = cache.key(llm.model, system, messages)
    if (cached := cache.get(key)) is not None:
        _log_call(cached, started, stream=True)
        yield cached.text
        yield cached
        return
    try:
        async for event in llm.stream(system, messages):
            if isinstance(event, LLMResult):
                cache.set(key, event)
                _log_call(event, started, stream=True)
            yield event
    except PROVIDER_ERRORS as e:
        logger.exception("llm.error", provider=llm.name)
        raise LLMError(f"Error del proveedor LLM: {e}") from e


def _estimation_messages(
    request: EstimationRequest, version: str
) -> tuple[str, list[Message]]:
    system, user = render_estimation_prompt(request, version)
    # system y user van separados: el system es estable (cacheable por el
    # proveedor), el user cambia en cada petición.
    return system, [{"role": "user", "content": user}]


async def generate_estimation(
    request: EstimationRequest, version: str = DEFAULT_VERSION
) -> LLMResult:
    """Genera una estimación a partir de los parámetros del formulario."""
    system, messages = _estimation_messages(request, version)
    return await complete(system, messages)


async def stream_estimation(
    request: EstimationRequest, version: str = DEFAULT_VERSION
) -> AsyncIterator[StreamEvent]:
    system, messages = _estimation_messages(request, version)
    async for event in stream(system, messages):
        yield event
