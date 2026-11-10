import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.config import settings
from app.routers import estimations, sessions


def configure_logging() -> None:
    """structlog: JSON en producción, salida legible en desarrollo."""
    renderer = (
        structlog.processors.JSONRenderer()
        if settings.app_env == "production"
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level]
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    structlog.get_logger().info(
        "app.start", provider=settings.llm_provider, model=settings.llm_model
    )
    yield


app = FastAPI(
    title="Estimador CAG",
    description=(
        "Genera estimaciones de proyectos de software a partir de la transcripción "
        "de una reunión con el cliente. Usa Cache-Augmented Generation: las "
        "estimaciones históricas viajan como contexto en cada llamada al LLM."
    ),
    version="0.5.0",
    lifespan=lifespan,
)
app.include_router(estimations.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "provider": settings.llm_provider,
        "model": settings.llm_model,
    }
