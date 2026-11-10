"""Sesiones conversacionales: memoria entre turnos + adjuntos."""

import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.prompts.loader import DEFAULT_VERSION, available_versions
from app.schemas import (
    AttachmentInfo,
    DetailLevel,
    OutputFormat,
    ProjectType,
    SessionCreated,
    SessionEstimationResponse,
    SessionState,
    TokenUsage,
)
from app.services.attachments import AttachmentError, ExtractedAttachment, extract_text
from app.services.conversation import run_turn, store
from app.services.providers import LLMError, LLMResult
from app.sessions import Session

router = APIRouter(prefix="/sessions", tags=["sessions"])

MAX_ATTACHMENTS = 5


def _get_session(session_id: str) -> Session:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada (¿se reinició el servicio?)")
    return session


def _state(session: Session) -> dict:
    return {
        "session_id": session.session_id,
        "project_metadata": session.metadata,
        "total_turns": session.history.total_turns,
        "turns_in_window": len(session.history),
        "max_turns": session.history.max_turns,
    }


def _usage(result: LLMResult) -> TokenUsage:
    return TokenUsage(
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        output_tokens=result.output_tokens,
    )


@router.post("", response_model=SessionCreated, status_code=201)
def create_session() -> SessionCreated:
    return SessionCreated(session_id=store.create().session_id)


@router.get("/{session_id}", response_model=SessionState)
def get_session(session_id: str) -> SessionState:
    return SessionState(**_state(_get_session(session_id)))


@router.post("/{session_id}/estimate", response_model=SessionEstimationResponse)
async def estimate_in_session(
    session_id: str,
    transcript: Annotated[str, Form(min_length=10, max_length=20_000)],
    project_type: Annotated[ProjectType, Form()] = ProjectType.WEB_SAAS,
    detail_level: Annotated[DetailLevel, Form()] = DetailLevel.MEDIUM,
    output_format: Annotated[OutputFormat, Form()] = OutputFormat.LINE_ITEMS,
    attachments: Annotated[list[UploadFile] | None, File(description="PDF, DOCX, TXT o MD")] = None,
    prompt_version: str = Query(DEFAULT_VERSION),
) -> SessionEstimationResponse:
    """Un turno de la conversación (multipart/form-data).

    La transcripción y los parámetros van como campos de formulario; los
    adjuntos, como archivos. El historial y el `project_metadata` de la sesión
    se actualizan con cada llamada.
    """
    session = _get_session(session_id)
    if prompt_version not in available_versions():
        raise HTTPException(status_code=422, detail=f"prompt_version desconocida: {prompt_version}")

    files = [f for f in attachments or [] if f.filename]  # Swagger manda un campo vacío
    if len(files) > MAX_ATTACHMENTS:
        raise HTTPException(status_code=422, detail=f"Máximo {MAX_ATTACHMENTS} adjuntos por turno")
    extracted: list[ExtractedAttachment] = []
    for upload in files:
        try:
            extracted.append(extract_text(upload.filename, await upload.read()))
        except AttachmentError as e:
            raise HTTPException(status_code=415, detail=str(e)) from e

    start = time.perf_counter()
    try:
        turn = await run_turn(
            session,
            transcript=transcript,
            attachments=extracted,
            project_type=project_type,
            detail_level=detail_level,
            output_format=output_format,
            version=prompt_version,
        )
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    costs = [r.cost_usd for r in (turn.estimation, turn.extraction) if r is not None]
    total_cost = None if any(c is None for c in costs) else round(sum(costs), 6)
    return SessionEstimationResponse(
        **_state(session),
        text=turn.estimation.text,
        prompt_version=prompt_version,
        attachments=[
            AttachmentInfo(filename=a.filename, chars=len(a.text), truncated=a.truncated)
            for a in extracted
        ],
        model=turn.estimation.model,
        provider=turn.estimation.provider,
        usage=_usage(turn.estimation),
        metadata_extraction_usage=_usage(turn.extraction) if turn.extraction else None,
        cost_usd=total_cost,
        duration_ms=round((time.perf_counter() - start) * 1000),
        created_at=datetime.now(UTC),
    )
