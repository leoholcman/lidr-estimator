"""Tier: a quién le hablamos, deducido del contexto de la conversación.

El tier cambia el encuadre de la respuesta (ejecutivo, PM, desarrollador o por
defecto). Se puede forzar desde la API; si no, se deduce con una cadena de
reglas en orden de precedencia. Se devuelve también el nombre de la regla que
ganó, para poder explicar por qué salió ese tier.
"""

import re
from collections.abc import Callable
from enum import Enum

from app.sessions import ProjectMetadata


class Tier(str, Enum):
    EXECUTIVE = "executive"
    PM = "pm"
    DEVELOPER = "developer"
    DEFAULT = "default"


_NDA = re.compile(r"\b(nda|confidencial|confidencialidad|non[- ]?disclosure)\b", re.IGNORECASE)
_REGULATORY = re.compile(r"\b(gdpr|rgpd|hipaa|pci[- ]?dss|iso[- ]?27001|sox)\b", re.IGNORECASE)
_DEV = re.compile(
    r"\b(docker|kubernetes|k8s|microservicios?|terraform|helm|grpc|graphql|kafka|airflow|rabbitmq|ci/cd)\b",
    re.IGNORECASE,
)

Rule = tuple[str, Tier, Callable[[str, ProjectMetadata], bool]]


def _text(transcript: str, metadata: ProjectMetadata) -> str:
    return f"{transcript}\n{metadata.agreed_scope or ''}"


RULES: tuple[Rule, ...] = (
    ("nda_detected", Tier.EXECUTIVE, lambda t, m: bool(_NDA.search(_text(t, m)))),
    ("regulatory_context", Tier.EXECUTIVE, lambda t, m: bool(_REGULATORY.search(_text(t, m)))),
    # una sola mención ("corre en docker") es ruido: pido dos términos distintos
    ("technical_audience", Tier.DEVELOPER, lambda t, m: len({x.lower() for x in _DEV.findall(t)}) >= 2),
    ("small_team_pm", Tier.PM, lambda t, m: m.assumed_team_size is not None and m.assumed_team_size <= 2),
)


def resolve_tier(
    transcript: str, metadata: ProjectMetadata, override: Tier | None = None
) -> tuple[Tier, str]:
    """Devuelve `(tier, regla)`. El override explícito gana siempre."""
    if override is not None:
        return override, "explicit_override"
    for name, tier, predicate in RULES:
        if predicate(transcript, metadata):
            return tier, name
    return Tier.DEFAULT, "default"
