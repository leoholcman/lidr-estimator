"""Carga y renderiza los prompts desde templates Jinja2 versionados."""

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.context.examples import ESTIMATION_EXAMPLES
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType

if TYPE_CHECKING:
    from app.services.attachments import ExtractedAttachment
    from app.sessions import ProjectMetadata

logger = structlog.get_logger()

PROMPTS_DIR = Path(__file__).parent
DEFAULT_VERSION = "v1"

_env = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    undefined=StrictUndefined,  # una variable que falta rompe, no queda vacía
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
    autoescape=False,
)


def available_versions(prompt: str = "estimation") -> list[str]:
    return sorted(p.name for p in (PROMPTS_DIR / prompt).iterdir() if p.is_dir())


def _render(name: str, **context) -> str:
    return _env.get_template(name).render(**context).strip()


def _render_estimation(version: str, **fields) -> tuple[str, str]:
    if version not in available_versions():
        raise ValueError(f"Versión de prompt desconocida: {version}")
    context = {
        "reference_projects": [],
        "attachments": [],
        "project_metadata": None,  # None = petición sin sesión (no hay bloque de memoria)
        "examples": ESTIMATION_EXAMPLES,
    } | fields
    system = _render(f"estimation/{version}/system.j2", **context)
    user = _render(f"estimation/{version}/user.j2", **context)

    logger.debug(
        "prompt.rendered",
        prompt="estimation",
        version=version,
        system_sha=hashlib.sha256(system.encode()).hexdigest()[:12],
        user_sha=hashlib.sha256(user.encode()).hexdigest()[:12],
    )
    return system, user


def render_estimation_prompt(
    request: EstimationRequest, version: str = DEFAULT_VERSION
) -> tuple[str, str]:
    """Devuelve `(system, user)` listos para mandar al modelo."""
    return _render_estimation(
        version,
        description=request.description,
        project_type=request.project_type.value,
        detail_level=request.detail_level.value,
        output_format=request.output_format.value,
        reference_projects=[r.model_dump() for r in request.reference_projects or []],
    )


def render_session_prompt(
    *,
    transcript: str,
    attachments: list["ExtractedAttachment"],
    project_type: ProjectType,
    detail_level: DetailLevel,
    output_format: OutputFormat,
    project_metadata: "ProjectMetadata",
    version: str = DEFAULT_VERSION,
) -> tuple[str, str]:
    """Prompt de un turno conversacional.

    El system lleva el bloque <project_metadata> (vacío en el primer turno) y el
    user lleva la transcripción con los adjuntos concatenados.
    """
    return _render_estimation(
        version,
        description=transcript,
        project_type=project_type.value,
        detail_level=detail_level.value,
        output_format=output_format.value,
        attachments=[vars(a) for a in attachments],
        project_metadata=project_metadata.model_dump(),
    )


def render_metadata_extraction_prompt(
    previous: "ProjectMetadata", user_message: str, assistant_message: str
) -> tuple[str, str]:
    system = _render("metadata_extraction/v1/system.j2")
    user = _render(
        "metadata_extraction/v1/user.j2",
        previous_metadata=previous.model_dump_json(),
        user_message=user_message,
        assistant_message=assistant_message,
    )
    return system, user
