from fastapi.testclient import TestClient

from app.context.examples import ESTIMATION_EXAMPLES
from app.main import app
from app.routers import estimations
from app.services.llm_service import SYSTEM_PROMPT, EstimationResult

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_system_prompt_includes_cag_examples():
    for example in ESTIMATION_EXAMPLES:
        assert example["meeting_summary"] in SYSTEM_PROMPT


def test_estimate_returns_llm_output(monkeypatch):
    async def fake_generate(transcript: str) -> EstimationResult:
        return EstimationResult(
            estimation="## Estimación: Test",
            model="gpt-4o-mini",
            provider="openai",
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=50,
        )

    monkeypatch.setattr(estimations, "generate_estimation", fake_generate)
    response = client.post(
        "/api/v1/estimate",
        json={"transcription": "El cliente necesita una landing page con formulario."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["estimation"] == "## Estimación: Test"
    assert body["provider"] == "openai"


def test_estimate_rejects_short_transcription():
    response = client.post("/api/v1/estimate", json={"transcription": "corto"})
    assert response.status_code == 422
