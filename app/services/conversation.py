"""Orquesta un turno de la conversación."""

import json
import re
import time
from dataclasses import dataclass, field

import structlog
from openai import OpenAIError
from pydantic import ValidationError

from app.compression import compress
from app.config import settings
from app.prompts.loader import (
    DEFAULT_VERSION,
    render_metadata_extraction_prompt,
    render_session_prompt,
    render_summary_prompt,
)
from app.schemas import DetailLevel, OutputFormat, ProjectType
from app.services import llm_service
from app.services.attachments import ExtractedAttachment
from app.services.providers import LLMError, LLMResult, Message
from app.services.semantic_cache import build_semantic_cache
from app.sessions import ProjectMetadata, Session, SessionStore, Turn
from app.tier import Tier, resolve_tier

logger = structlog.get_logger()

store = SessionStore(max_turns=settings.max_turns)
semantic_cache = build_semantic_cache()

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class TurnResult:
    estimation: LLMResult
    cache_hit_kind: str  # "none" | "exact" | "semantic"
    tier: Tier
    tier_rule: str
    messages_sent: int  # mensajes user/assistant enviados al LLM (sin el system)
    # todas las llamadas al LLM del turno: estimación, extractor y resumen
    calls: list[LLMResult] = field(default_factory=list)
    observation: dict = field(default_factory=dict)  # el evento turn_observed


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


async def _estimate(
    session: Session, system: str, messages: list[Message], bucket: str, user: str
) -> tuple[LLMResult, str]:
    """Estimación con las dos cachés: primero la exacta, después la semántica."""
    if llm_service.is_cached(system, messages):
        return await llm_service.complete(system, messages), "exact"

    first_turn = session.history.total_turns == 0
    vector = None
    if first_turn and semantic_cache is not None:
        try:
            hit, vector = await semantic_cache.lookup(bucket, user)
        except OpenAIError as e:  # sin embeddings seguimos sin caché semántica
            logger.warning("semantic_cache.failed", error=str(e)[:200])
            hit = None
        if hit is not None:
            return hit, "semantic"

    result = await llm_service.complete(system, messages)
    if vector is not None:
        semantic_cache.store(bucket, vector, result)
    return result, "none"


async def run_turn(
    session: Session,
    *,
    transcript: str,
    attachments: list[ExtractedAttachment],
    project_type: ProjectType,
    detail_level: DetailLevel,
    output_format: OutputFormat,
    tier_override: Tier | None = None,
    version: str = DEFAULT_VERSION,
) -> TurnResult:
    async with session.lock:
        started = time.perf_counter()
        history = session.history
        calls: list[LLMResult] = []

        tier, tier_rule = resolve_tier(transcript, session.metadata, tier_override)
        system, user = render_session_prompt(
            transcript=transcript,
            attachments=attachments,
            project_type=project_type,
            detail_level=detail_level,
            output_format=output_format,
            project_metadata=session.metadata,
            anchors=history.anchors,
            summary=history.summary,
            tier=tier.value,
            version=version,
        )
        messages = history.to_messages_list(system, pending_user=user)
        attachment_chars = sum(len(a.text) for a in attachments)
        bucket = ":".join([
            version, project_type.value, detail_level.value, output_format.value,
            tier.value, str(attachment_chars),
        ])
        # to_messages_list incluye el system como primer mensaje; los
        # proveedores lo reciben aparte.
        estimation, cache_hit_kind = await _estimate(session, system, messages[1:], bucket, user)
        calls.append(estimation)

        history.add_turn(transcript, user, estimation.text)

        async def summarize(previous: str | None, evicted: list[Turn]) -> str:
            summary_system, summary_user = render_summary_prompt(previous, evicted)
            try:
                result = await llm_service.complete(
                    summary_system, [{"role": "user", "content": summary_user}]
                )
            except LLMError as e:
                logger.warning("summarizer.failed", error=str(e)[:200])
                return previous or ""
            calls.append(result)
            return result.text.strip()

        await compress(history, summarize)

        session.metadata, extraction = await extract_metadata(
            session.metadata, user, estimation.text
        )
        if extraction is not None:
            calls.append(extraction)
        session.last_resolved_tier = tier.value
        session.last_tier_rule = tier_rule

        # Un único evento por turno con todo lo medible junto: se vuelca a CSV
        # de una pasada, sin reconciliar cinco logs por timestamp.
        billed = [c for c in calls if not c.cache_hit]
        costs = [c.cost_usd for c in calls]
        observation = {
            "turn_index": history.total_turns,
            "session_id": session.session_id,
            "enriched_transcript_chars": len(transcript) + attachment_chars,
            "attachments_total_chars": attachment_chars,
            "messages_in_window": len(history) * 2,
            "anchors_count": len(history.anchors),
            "summary_chars": len(history.summary or ""),
            "tokens_in": sum(c.input_tokens for c in billed),
            "tokens_out": sum(c.output_tokens for c in billed),
            "cost_usd": None if any(c is None for c in costs) else round(sum(costs), 6),
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "cache_hit_kind": cache_hit_kind,
            "last_resolved_tier": tier.value,
        }
        session.last_turn = observation
        logger.info("turn_observed", **observation, llm_calls=len(calls))
        return TurnResult(
            estimation=estimation,
            cache_hit_kind=cache_hit_kind,
            tier=tier,
            tier_rule=tier_rule,
            messages_sent=len(messages) - 1,
            calls=calls,
            observation=observation,
        )
