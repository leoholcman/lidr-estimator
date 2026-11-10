"""Carga y renderiza los prompts desde templates Jinja2 versionados."""

import hashlib
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.context.examples import ESTIMATION_EXAMPLES
from app.schemas import EstimationRequest

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


def render_estimation_prompt(
    request: EstimationRequest, version: str = DEFAULT_VERSION
) -> tuple[str, str]:
    """Devuelve `(system, user)` listos para mandar al modelo."""
    if version not in available_versions():
        raise ValueError(f"Versión de prompt desconocida: {version}")

    context = {
        "description": request.description,
        "project_type": request.project_type.value,
        "detail_level": request.detail_level.value,
        "output_format": request.output_format.value,
        "reference_projects": [r.model_dump() for r in request.reference_projects or []],
        "examples": ESTIMATION_EXAMPLES,
    }
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
