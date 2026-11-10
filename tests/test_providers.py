import anthropic
import httpx

from app.services import llm_service
from app.services.providers import FallbackProvider, LLMResult
from tests.fakes import FakeProvider

MESSAGES = [{"role": "user", "content": "hola"}]


def _api_error() -> anthropic.APIError:
    request = httpx.Request("POST", "https://api.anthropic.com")
    return anthropic.APIConnectionError(request=request)


async def test_fallback_uses_secondary_when_primary_fails():
    primary = FakeProvider(fail=_api_error())
    secondary = FakeProvider(text="desde el secundario")
    result = await FallbackProvider(primary, secondary).complete("sys", MESSAGES)
    assert result.text == "desde el secundario"


async def test_fallback_stream_switches_before_first_token():
    primary = FakeProvider(fail=_api_error())
    secondary = FakeProvider(text="hola mundo")
    events = [e async for e in FallbackProvider(primary, secondary).stream("sys", MESSAGES)]
    assert isinstance(events[-1], LLMResult)
    assert events[-1].text == "hola mundo"


async def test_exact_match_cache_avoids_second_call(fake_llm):
    first = await llm_service.complete(MESSAGES)
    second = await llm_service.complete(MESSAGES)
    assert len(fake_llm.calls) == 1
    assert not first.cache_hit and second.cache_hit
    assert second.cost_usd == 0.0


async def test_cache_distinguishes_different_conversations(fake_llm):
    await llm_service.complete(MESSAGES)
    await llm_service.complete([{"role": "user", "content": "otra cosa"}])
    assert len(fake_llm.calls) == 2
