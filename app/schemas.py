"""Schemas de request y response."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.sessions import ProjectMetadata


class ProjectType(str, Enum):
    MOBILE_APP = "mobile_app"
    WEB_SAAS = "web_saas"
    INTERNAL_TOOL = "internal_tool"
    DATA_PIPELINE = "data_pipeline"


class DetailLevel(str, Enum):
    SUMMARY = "summary"
    MEDIUM = "medium"
    DETAILED = "detailed"


class OutputFormat(str, Enum):
    PHASES_TABLE = "phases_table"
    LINE_ITEMS = "line_items"
    NARRATIVE = "narrative"


class ReferenceProject(BaseModel):
    """Proyecto similar ya entregado, para calibrar la estimación (opcional)."""

    name: str = Field(min_length=2, max_length=120)
    summary: str = Field(min_length=5, max_length=500)
    actual_hours: int = Field(gt=0, le=10_000)


class EstimationRequest(BaseModel):
    description: str = Field(
        min_length=20,
        max_length=2000,
        description="Descripción del proyecto o transcripción de la reunión",
    )
    project_type: ProjectType
    detail_level: DetailLevel
    output_format: OutputFormat
    reference_projects: list[ReferenceProject] | None = Field(default=None, max_length=5)


class TokenUsage(BaseModel):
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


class EstimationResponse(BaseModel):
    text: str
    prompt_version: str
    # Metadatos de la llamada (observabilidad)
    model: str
    provider: str
    usage: TokenUsage
    cost_usd: float | None
    cache_hit: bool
    duration_ms: int
    created_at: datetime


class PromptPreview(BaseModel):
    prompt_version: str
    system: str
    user: str


class SessionCreated(BaseModel):
    session_id: str


class AttachmentInfo(BaseModel):
    filename: str
    chars: int
    truncated: bool


class SessionState(BaseModel):
    session_id: str
    project_metadata: ProjectMetadata
    total_turns: int
    turns_in_window: int
    max_turns: int


class SessionEstimationResponse(SessionState):
    text: str
    prompt_version: str
    attachments: list[AttachmentInfo]
    model: str
    provider: str
    usage: TokenUsage
    metadata_extraction_usage: TokenUsage | None
    cost_usd: float | None = Field(description="Coste total del turno (estimación + extracción)")
    duration_ms: int
    created_at: datetime
