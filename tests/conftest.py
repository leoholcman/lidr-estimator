import os

import pytest

# Los tests no llaman a ningún proveedor: basta con una key de mentira.
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.services import llm_service
from tests.fakes import FakeProvider


@pytest.fixture
def fake_llm(monkeypatch):
    """Reemplaza el proveedor real por uno falso y vacía la caché."""
    fake = FakeProvider()
    monkeypatch.setattr(llm_service, "_provider", fake)
    llm_service.cache.clear()
    return fake
