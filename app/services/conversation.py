"""Orquesta un turno de la conversación."""

import json
import re
from dataclasses import dataclass

import structlog
from pydantic import ValidationError

from app.config import settings
from app.prompts.loader import (
    DEFAULT_VERSION,
    render_metadata_extraction_prompt,
    render_session_prompt,
)
from app.schemas import DetailLevel, OutputFormat, ProjectType
from app.services import llm_service
from app.services.attachments import ExtractedAttachment
from app.services.providers import LLMError, LLMResult
from app.sessions import ProjectMetadata, Session, SessionStore

logger = structlog.get_logger()

store = SessionStore(max_turns=settings.max_turns)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class TurnResult:
    estimation: LLMResult
    extraction: LLMResult | None
    messages_sent: int  # mensajes user/assistant enviados al LLM (sin el system)


def _parse_metadata(text: str) -> ProjectMetadata:
    """Extrae el JSON aunque el modelo lo envuelva en ```json ... ```."""
    match = _JSON_OBJECT.search(text)
    if not match:
        raise ValueError("la respuesta no contiene un objeto JSON")
    return ProjectMetadata.model_validate(json.loads(match.group(0)))


async def extract_metadata(
    previous: ProjectMetadata, user_message: str, assistant_message: str
) -> tuple[ProjectMetadata, LLMResult | None]:
    """Segunda llamada al LLM que devuelve los hechos del proyecto en JSON.

    Si falla (red, JSON inválido) se conserva la memoria anterior: perder una
    actualización es preferible a romper el turno del usuario.
    """
    system, user = render_metadata_extraction_prompt(previous, user_message, assistant_message)
    try:
        result = await llm_service.complete(system, [{"role": "user", "content": user}])
        update = _parse_metadata(result.text)
    except (LLMError, ValueError, ValidationError) as e:
        logger.warning("metadata.extraction_failed", error=str(e))
        return previous, None
    merged = previous.merge(update)
    logger.info("metadata.updated", **merged.model_dump())
    return merged, result


async def run_turn(
    session: Session,
    *,
    transcript: str,
    attachments: list[ExtractedAttachment],
    project_type: ProjectType,
    detail_level: DetailLevel,
    output_format: OutputFormat,
    version: str = DEFAULT_VERSION,
) -> TurnResult:
    async with session.lock:
        system, user = render_session_prompt(
            transcript=transcript,
            attachments=attachments,
            project_type=project_type,
            detail_level=detail_level,
            output_format=output_format,
            project_metadata=session.metadata,
            version=version,
        )
        messages = session.history.to_messages_list(system, pending_user=user)
        # to_messages_list incluye el system como primer mensaje; los
        # proveedores lo reciben aparte.
        estimation = await llm_service.complete(messages[0]["content"], messages[1:])

        session.history.add_turn(user, estimation.text)
        session.metadata, extraction = await extract_metadata(
            session.metadata, user, estimation.text
        )
        logger.info(
            "session.turn",
            session_id=session.session_id,
            turn=session.history.total_turns,
            turns_in_window=len(session.history),
            messages_sent=len(messages) - 1,
            attachments=[a.filename for a in attachments],
        )
        return TurnResult(estimation, extraction, messages_sent=len(messages) - 1)
