from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    llm_provider: Literal["openai", "anthropic"] = "openai"
    llm_model: str = "gpt-4o-mini"
    # Si el proveedor principal falla, prueba con el otro (si tiene API key)
    llm_fallback: bool = True
    cache_ttl_seconds: int = 3600
    app_env: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # URL del servicio IA que usa el cliente Streamlit
    api_base_url: str = "http://localhost:8000"

    @model_validator(mode="after")
    def check_provider_key(self) -> "Settings":
        # La API key solo es obligatoria para el proveedor seleccionado
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY es requerida cuando LLM_PROVIDER=openai")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY es requerida cuando LLM_PROVIDER=anthropic")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
