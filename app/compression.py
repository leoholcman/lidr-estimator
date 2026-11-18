"""Compresión del historial: qué pasa con los turnos que salen de la ventana.

Antes se descartaban. Ahora cada turno que sale va a uno de dos lugares:

- Si trae un compromiso duradero (presupuesto cerrado, NDA, alcance congelado,
  fecha límite...) se guarda textual como **ancla**.
- Si no, se suma al **resumen acumulativo** con una llamada al LLM.

La detección de anclas es por reglas (regex): es gratis y determinista. Prefiero
que se le escape alguna a que marque de más, porque las anclas no se borran
nunca y cada una ocupa prompt en todos los turnos siguientes.
"""

import re
from collections.abc import Awaitable, Callable

import structlog

from app.sessions import ConversationHistory, Turn

logger = structlog.get_logger()

MAX_ANCHOR_CHARS = 600

ANCHOR_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("nda", re.compile(r"\b(nda|confidencialidad|non[- ]?disclosure)\b", re.IGNORECASE)),
    ("contrato_firmado", re.compile(r"\b(firm[oó]|firmamos|firmado|signed)\b.{0,40}\b(contrato|acuerdo|sow|contract)\b", re.IGNORECASE)),
    ("alcance_cerrado", re.compile(r"\b(alcance|scope|backlog)\b.{0,30}\b(cerrado|congelado|definitivo|frozen|locked)\b", re.IGNORECASE)),
    ("presupuesto_cerrado", re.compile(r"\bpresupuesto\b.{0,40}\b(cerrado|aprobado|m[aá]ximo|tope|fijo)\b|\b(budget)\b.{0,20}\b(locked|approved|capped)\b", re.IGNORECASE)),
    ("normativa", re.compile(r"\b(gdpr|rgpd|hipaa|pci[- ]?dss|iso[- ]?27001|sox)\b", re.IGNORECASE)),
    ("fecha_limite", re.compile(r"\b(fecha l[ií]mite|deadline|s[ií] o s[ií] antes del?|no puede pasar del?)\b", re.IGNORECASE)),
    ("compromiso", re.compile(r"\b(queda confirmado|qued[oó] acordado|acordamos que|nos comprometimos a)\b", re.IGNORECASE)),
)

Summarizer = Callable[[str | None, list[Turn]], Awaitable[str]]


def anchor_rules(text: str) -> list[str]:
    """Nombres de las reglas que disparan sobre el texto (vacío si no es ancla)."""
    return [name for name, pattern in ANCHOR_RULES if pattern.search(text)]


async def compress(history: ConversationHistory, summarize: Summarizer) -> None:
    """Reparte los turnos que sobran de la ventana entre anclas y resumen."""
    evicted = history.overflow()
    if not evicted:
        return
    to_summary: list[Turn] = []
    promoted: list[str] = []
    for turn in evicted:
        rules = anchor_rules(turn.transcript)
        if rules:
            history.anchors.append(turn.transcript[:MAX_ANCHOR_CHARS])
            promoted.extend(rules)
        else:
            to_summary.append(turn)
    if to_summary:
        history.summary = await summarize(history.summary, to_summary)
    logger.info(
        "history.compressed",
        promoted_anchors=len(evicted) - len(to_summary),
        anchor_rules=promoted,
        evicted_to_summary=len(to_summary),
        summary_chars=len(history.summary or ""),
        anchors_count=len(history.anchors),
    )
