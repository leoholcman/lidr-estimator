"""Wrapper de proveedores (OpenAI / Anthropic) con fallback."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

import anthropic
import openai
import structlog
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

logger = structlog.get_logger()

Message = dict[str, str]  # {"role": "user" | "assistant", "content": "..."}

DEFAULT_MODELS = {"openai": "gpt-4o-mini", "anthropic": "claude-haiku-4-5"}

# USD por millón de tokens: (input, input cacheado, output)
PRICES_PER_MTOK = {
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "claude-haiku-4-5": (1.00, 0.10, 5.00),
    "claude-haiku-5-5": (0.10, 0.01, 0.50),
}

PROVIDER_ERRORS = (anthropic.APIError, openai.APIError)


class LLMError(RuntimeError):
    """Error del proveedor que la API traduce a un 502."""


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str
    input_tokens: int  # incluye los cacheados
    cached_input_tokens: int
    output_tokens: int
    cache_hit: bool = False

    @property
    def cost_usd(self) -> float | None:
        if self.cache_hit:
            return 0.0  # salió de nuestra caché: no hubo llamada al proveedor
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


# Lo que emite `stream()`: fragmentos de texto y, al final, el resultado completo.
StreamEvent = str | LLMResult


class LLMProvider(ABC):
    name: str

    def __init__(self, model: str, max_tokens: int = 8192):
        self.model = model
        self.max_tokens = max_tokens

    @abstractmethod
    async def complete(self, system: str, messages: list[Message]) -> LLMResult: ...

    @abstractmethod
    def stream(self, system: str, messages: list[Message]) -> AsyncIterator[StreamEvent]: ...


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_tokens: int = 8192):
        super().__init__(model, max_tokens)
        self.client = AsyncAnthropic(api_key=api_key)

    def _kwargs(self, system: str, messages: list[Message]) -> dict:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            # cache_control: el system prompt es idéntico entre llamadas (CAG),
            # así Anthropic lo cachea y las siguientes llamadas cuestan menos.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
        }

    def _result(self, text: str, usage, stop_reason: str | None) -> LLMResult:
        if stop_reason == "max_tokens":
            raise LLMError("La respuesta se cortó por max_tokens")
        cached = usage.cache_read_input_tokens or 0
        created = usage.cache_creation_input_tokens or 0
        return LLMResult(
            text=text,
            model=self.model,
            provider=self.name,
            input_tokens=usage.input_tokens + cached + created,
            cached_input_tokens=cached,
            output_tokens=usage.output_tokens,
        )

    async def complete(self, system: str, messages: list[Message]) -> LLMResult:
        response = await self.client.messages.create(**self._kwargs(system, messages))
        text = "".join(b.text for b in response.content if b.type == "text")
        return self._result(text, response.usage, response.stop_reason)

    async def stream(self, system: str, messages: list[Message]) -> AsyncIterator[StreamEvent]:
        async with self.client.messages.stream(**self._kwargs(system, messages)) as stream:
            async for delta in stream.text_stream:
                yield delta
            final = await stream.get_final_message()
        text = "".join(b.text for b in final.content if b.type == "text")
        yield self._result(text, final.usage, final.stop_reason)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, max_tokens: int = 8192):
        super().__init__(model, max_tokens)
        self.client = AsyncOpenAI(api_key=api_key)

    def _messages(self, system: str, messages: list[Message]) -> list[Message]:
        return [{"role": "system", "content": system}, *messages]

    def _result(self, text: str, usage, finish_reason: str | None) -> LLMResult:
        if finish_reason == "length":
            raise LLMError("La respuesta se cortó por max_tokens")
        details = usage.prompt_tokens_details if usage else None
        return LLMResult(
            text=text,
            model=self.model,
            provider=self.name,
            input_tokens=usage.prompt_tokens if usage else 0,
            cached_input_tokens=(details.cached_tokens or 0) if details else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    async def complete(self, system: str, messages: list[Message]) -> LLMResult:
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=self._messages(system, messages),
        )
        choice = response.choices[0]
        return self._result(choice.message.content or "", response.usage, choice.finish_reason)

    async def stream(self, system: str, messages: list[Message]) -> AsyncIterator[StreamEvent]:
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=self._messages(system, messages),
            stream=True,
            stream_options={"include_usage": True},
        )
        parts: list[str] = []
        usage = None
        finish_reason = None
        async for chunk in response:
            if chunk.usage:
                usage = chunk.usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish_reason = choice.finish_reason or finish_reason
            if choice.delta.content:
                parts.append(choice.delta.content)
                yield choice.delta.content
        yield self._result("".join(parts), usage, finish_reason)


class FallbackProvider(LLMProvider):
    """Usa `primary` y, si falla, `secondary`.

    En streaming solo se cambia de proveedor si el error llega antes del
    primer token: a mitad de respuesta ya no se puede cambiar sin duplicar texto.
    """

    def __init__(self, primary: LLMProvider, secondary: LLMProvider):
        self.primary = primary
        self.secondary = secondary
        self.name = primary.name
        self.model = primary.model

    async def complete(self, system: str, messages: list[Message]) -> LLMResult:
        try:
            return await self.primary.complete(system, messages)
        except PROVIDER_ERRORS as e:
            logger.warning("llm.fallback", failed=self.primary.name, error=str(e))
            return await self.secondary.complete(system, messages)

    async def stream(self, system: str, messages: list[Message]) -> AsyncIterator[StreamEvent]:
        started = False
        try:
            async for event in self.primary.stream(system, messages):
                started = True
                yield event
            return
        except PROVIDER_ERRORS as e:
            if started:
                raise
            logger.warning("llm.fallback", failed=self.primary.name, error=str(e))
        async for event in self.secondary.stream(system, messages):
            yield event


def build_provider(name: str, settings, model: str | None = None) -> LLMProvider:
    model = model or DEFAULT_MODELS[name]
    if name == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key, model)
    return OpenAIProvider(settings.openai_api_key, model)


def get_provider(settings) -> LLMProvider:
    primary = build_provider(settings.llm_provider, settings, settings.llm_model)
    other = "anthropic" if settings.llm_provider == "openai" else "openai"
    other_key = settings.anthropic_api_key if other == "anthropic" else settings.openai_api_key
    if settings.llm_fallback and other_key:
        return FallbackProvider(primary, build_provider(other, settings))
    return primary
