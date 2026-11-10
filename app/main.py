import logging

from fastapi import FastAPI

from app.config import settings
from app.routers import estimations

logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="Estimador CAG",
    description=(
        "Genera estimaciones de proyectos de software a partir de la transcripción "
        "de una reunión con el cliente. Usa Cache-Augmented Generation: las "
        "estimaciones históricas viajan como contexto en cada llamada al LLM."
    ),
    version="0.1.0",
)
app.include_router(estimations.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "provider": settings.llm_provider,
        "model": settings.llm_model,
    }
