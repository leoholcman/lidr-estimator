"""Lógica de llamada al LLM.

CAG: los ejemplos de estimaciones previas viajan en el system prompt de cada
llamada. No hay retrieval: todo el contexto está precargado.
"""

from dataclasses import dataclass

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config import settings
from app.context.examples import ESTIMATION_EXAMPLES

MAX_TOKENS = 8192

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
- Si la transcripción no describe un proyecto de software, indícalo y no estimes."""


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


# USD por millón de tokens: (input, input cacheado, output)
PRICES_PER_MTOK = {
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "claude-haiku-4-5": (1.00, 0.10, 5.00),
    "claude-haiku-5-5": (0.10, 0.01, 0.50),
}


@dataclass
class EstimationResult:
    estimation: str
    model: str
    provider: str
    input_tokens: int  # incluye los cacheados
    cached_input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float | None:
        prices = PRICES_PER_MTOK.get(self.model)
        if prices is None:
            return None
        input_price, cached_price, output_price = prices
        uncached = self.input_tokens - self.cached_input_tokens
        cost = (
            uncached * input_price
            + self.cached_input_tokens * cached_price
            + self.output_tokens * output_price
        ) / 1_000_000
        return round(cost, 6)


async def _call_anthropic(transcript: str) -> EstimationResult:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.llm_model,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": transcript}],
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("La estimación se cortó por max_tokens")
    usage = response.usage
    cached = usage.cache_read_input_tokens or 0
    return EstimationResult(
        estimation="".join(b.text for b in response.content if b.type == "text"),
        model=settings.llm_model,
        provider="anthropic",
        input_tokens=usage.input_tokens + cached + (usage.cache_creation_input_tokens or 0),
        cached_input_tokens=cached,
        output_tokens=usage.output_tokens,
    )


async def _call_openai(transcript: str) -> EstimationResult:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.llm_model,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
    )
    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError("La estimación se cortó por max_tokens")
    usage = response.usage
    details = usage.prompt_tokens_details
    return EstimationResult(
        estimation=choice.message.content or "",
        model=settings.llm_model,
        provider="openai",
        input_tokens=usage.prompt_tokens,
        cached_input_tokens=(details.cached_tokens or 0) if details else 0,
        output_tokens=usage.completion_tokens,
    )


async def generate_estimation(transcript: str) -> EstimationResult:
    """Genera una estimación a partir de la transcripción de una reunión."""
    if settings.llm_provider == "anthropic":
        return await _call_anthropic(transcript)
    return await _call_openai(transcript)
