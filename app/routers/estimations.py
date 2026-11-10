import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services import llm_service
from app.services.llm_service import generate_estimation
from app.services.providers import LLMError, LLMResult

router = APIRouter(tags=["estimations"])


class EstimationRequest(BaseModel):
    transcription: str = Field(
        min_length=20,
        description="Transcripción de la reunión con el cliente",
        examples=["En la reunión con el cliente se discutió la necesidad de..."],
    )


class TokenUsage(BaseModel):
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


class EstimationResponse(BaseModel):
    estimation: str
    model: str
    provider: str
    usage: TokenUsage
    cost_usd: float | None = Field(description="Coste estimado de la llamada al LLM")
    cache_hit: bool
    duration_ms: int
    created_at: datetime


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, description="Historial; el último es del usuario")


def _usage(result: LLMResult) -> TokenUsage:
    return TokenUsage(
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        output_tokens=result.output_tokens,
    )


@router.post("/estimate", response_model=EstimationResponse)
async def estimate(request: EstimationRequest) -> EstimationResponse:
    start = time.perf_counter()
    try:
        result = await generate_estimation(request.transcription)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return EstimationResponse(
        estimation=result.text,
        model=result.model,
        provider=result.provider,
        usage=_usage(result),
        cost_usd=result.cost_usd,
        cache_hit=result.cache_hit,
        duration_ms=round((time.perf_counter() - start) * 1000),
        created_at=datetime.now(UTC),
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Conversación con el estimador, en streaming.

    Devuelve NDJSON (un JSON por línea):
    `{"type": "delta", "text": "..."}` por cada fragmento,
    y al final `{"type": "done", ...métricas}` o `{"type": "error", "detail": "..."}`.
    """
    if request.messages[-1].role != "user":
        raise HTTPException(status_code=422, detail="El último mensaje debe ser del usuario")
    messages = [m.model_dump() for m in request.messages]

    async def events() -> AsyncIterator[str]:
        start = time.perf_counter()
        try:
            async for event in llm_service.stream(messages):
                if isinstance(event, LLMResult):
                    done = {
                        "type": "done",
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


@router.get("/context")
def context() -> dict[str, str]:
    """System prompt activo (instrucciones + ejemplos CAG). Lo muestra el cliente."""
    return {"system_prompt": llm_service.SYSTEM_PROMPT}
