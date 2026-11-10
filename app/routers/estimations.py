import logging
import time
from datetime import UTC, datetime

import anthropic
import openai
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.llm_service import generate_estimation

logger = logging.getLogger(__name__)

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
    duration_ms: int
    created_at: datetime


@router.post("/estimate", response_model=EstimationResponse)
async def estimate(request: EstimationRequest) -> EstimationResponse:
    start = time.perf_counter()
    try:
        result = await generate_estimation(request.transcription)
    except (anthropic.APIError, openai.APIError) as e:
        logger.exception("Error del proveedor LLM")
        raise HTTPException(status_code=502, detail=f"Error del proveedor LLM: {e}") from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return EstimationResponse(
        estimation=result.estimation,
        model=result.model,
        provider=result.provider,
        usage=TokenUsage(
            input_tokens=result.input_tokens,
            cached_input_tokens=result.cached_input_tokens,
            output_tokens=result.output_tokens,
        ),
        cost_usd=result.cost_usd,
        duration_ms=round((time.perf_counter() - start) * 1000),
        created_at=datetime.now(UTC),
    )
