"""Lógica de llamada al LLM.

CAG: los ejemplos de estimaciones previas viajan en el system prompt de cada
llamada. No hay retrieval: todo el contexto está precargado.
"""

import time
from collections.abc import AsyncIterator

import structlog

from app.config import settings
from app.context.examples import ESTIMATION_EXAMPLES
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

INSTRUCTIONS = """\
Eres un estimador experto de proyectos de software. Recibirás la transcripción \
de una reunión con un cliente y debes generar una estimación del proyecto.

Basa tus estimaciones en los ejemplos de estimaciones previas que aparecen más \
abajo: son proyectos reales de nuestro equipo y reflejan nuestros tiempos de \
desarrollo asistido por IA, nuestra tarifa (USD 35/h) y nuestro criterio de \
contingencia. Compara el nuevo proyecto con ellos para calibrar las horas.

Reglas:
- Responde en español, en markdown, siguiendo exactamente el formato de los ejemplos.
- Desglosa el trabajo en tareas concretas con sus horas; el subtotal debe ser la suma exacta.
- Aplica una contingencia del 15%, o del 20% si hay integraciones con terceros o \
publicación en stores, y redondea a horas enteras.
- Calcula el coste total con la tarifa de USD 35/h.
- Si la transcripción deja dudas sobre el alcance, decláralas como supuestos en \
lugar de inventar requisitos. Lista lo que queda fuera de alcance.
- Cualquier web, app, integración o automatización cuenta como proyecto de software, \
aunque la descripción sea breve. Solo si el texto no tiene nada que ver con \
construir software, indícalo y no estimes.
- Si en la conversación el usuario pide cambios o aclaraciones sobre una estimación \
anterior, ajústala y devuelve la estimación completa actualizada."""


def _format_examples() -> str:
    blocks = []
    for i, example in enumerate(ESTIMATION_EXAMPLES, start=1):
        blocks.append(
            f'<ejemplo numero="{i}">\n'
            f"<resumen_reunion>\n{example['meeting_summary']}\n</resumen_reunion>\n"
            f"<estimacion>\n{example['estimation']}\n</estimacion>\n"
            f"</ejemplo>"
        )
    return "\n\n".join(blocks)


# Se construye una sola vez: un system prompt idéntico entre llamadas permite
# que el proveedor lo cachee (prompt caching).
SYSTEM_PROMPT = (
    f"{INSTRUCTIONS}\n\n"
    f"<estimaciones_previas>\n{_format_examples()}\n</estimaciones_previas>"
)

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


async def complete(messages: list[Message], system: str = SYSTEM_PROMPT) -> LLMResult:
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


async def stream(
    messages: list[Message], system: str = SYSTEM_PROMPT
) -> AsyncIterator[StreamEvent]:
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


async def generate_estimation(transcript: str) -> LLMResult:
    """Genera una estimación a partir de la transcripción de una reunión."""
    return await complete([{"role": "user", "content": transcript}])
