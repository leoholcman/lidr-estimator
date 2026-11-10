import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.prompts.loader import DEFAULT_VERSION, available_versions, render_estimation_prompt
from app.schemas import EstimationRequest, EstimationResponse, PromptPreview, TokenUsage
from app.services import llm_service
from app.services.providers import LLMError, LLMResult

router = APIRouter(tags=["estimations"])

PromptVersion = Query(DEFAULT_VERSION, description="Versión del prompt (v1, v2...)")


def _check_version(version: str) -> None:
    if version not in available_versions():
        raise HTTPException(
            status_code=422,
            detail=f"prompt_version desconocida: {version}. Disponibles: {available_versions()}",
        )


def _usage(result: LLMResult) -> TokenUsage:
    return TokenUsage(
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        output_tokens=result.output_tokens,
    )


@router.post("/estimate", response_model=EstimationResponse)
async def estimate(
    request: EstimationRequest, prompt_version: str = PromptVersion
) -> EstimationResponse:
    _check_version(prompt_version)
    start = time.perf_counter()
    try:
        result = await llm_service.generate_estimation(request, prompt_version)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return EstimationResponse(
        text=result.text,
        prompt_version=prompt_version,
        model=result.model,
        provider=result.provider,
        usage=_usage(result),
        cost_usd=result.cost_usd,
        cache_hit=result.cache_hit,
        duration_ms=round((time.perf_counter() - start) * 1000),
        created_at=datetime.now(UTC),
    )


@router.post("/estimate/stream")
async def estimate_stream(
    request: EstimationRequest, prompt_version: str = PromptVersion
) -> StreamingResponse:
    """Igual que /estimate pero en streaming.

    Devuelve NDJSON (un JSON por línea):
    `{"type": "delta", "text": "..."}` por cada fragmento,
    y al final `{"type": "done", ...métricas}` o `{"type": "error", "detail": "..."}`.
    """
    _check_version(prompt_version)

    async def events() -> AsyncIterator[str]:
        start = time.perf_counter()
        try:
            async for event in llm_service.stream_estimation(request, prompt_version):
                if isinstance(event, LLMResult):
                    done = {
                        "type": "done",
                        "prompt_version": prompt_version,
                        "model": event.model,
                        "provider": event.provider,
                        "usage": _usage(event).model_dump(),
                        "cost_usd": event.cost_usd,
                        "cache_hit": event.cache_hit,
                        "duration_ms": round((time.perf_counter() - start) * 1000),
                    }
                    yield json.dumps(done) + "\n"
                else:
                    yield json.dumps({"type": "delta", "text": event}) + "\n"
        except LLMError as e:
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


@router.post("/prompt/preview", response_model=PromptPreview)
def prompt_preview(
    request: EstimationRequest, prompt_version: str = PromptVersion
) -> PromptPreview:
    """Muestra el prompt que se mandaría al modelo, sin llamarlo (debug)."""
    _check_version(prompt_version)
    system, user = render_estimation_prompt(request, prompt_version)
    return PromptPreview(prompt_version=prompt_version, system=system, user=user)


@router.get("/prompt/versions")
def prompt_versions() -> dict[str, list[str] | str]:
    return {"versions": available_versions(), "default": DEFAULT_VERSION}
