import json

from fastapi.testclient import TestClient

from app.context.examples import ESTIMATION_EXAMPLES
from app.main import app
from app.services.llm_service import SYSTEM_PROMPT

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_system_prompt_includes_cag_examples():
    for example in ESTIMATION_EXAMPLES:
        assert example["meeting_summary"] in SYSTEM_PROMPT


def test_estimate_returns_llm_output(fake_llm):
    response = client.post(
        "/api/v1/estimate",
        json={"transcription": "El cliente necesita una landing page con formulario."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["estimation"] == "## Estimación: Test"
    assert body["usage"]["output_tokens"] == 20
    system, messages = fake_llm.calls[0]
    assert system == SYSTEM_PROMPT
    assert messages[-1]["role"] == "user"


def test_estimate_rejects_short_transcription():
    response = client.post("/api/v1/estimate", json={"transcription": "corto"})
    assert response.status_code == 422


def test_chat_stream_emits_deltas_then_metrics(fake_llm):
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"messages": [{"role": "user", "content": "Necesito una app de reservas"}]},
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]
    deltas = [e for e in events if e["type"] == "delta"]
    assert len(deltas) > 1  # llegó en varios fragmentos
    assert "".join(e["text"] for e in deltas).strip() == "## Estimación: Test"
    assert events[-1]["type"] == "done"
    assert events[-1]["usage"]["input_tokens"] == 100


def test_chat_stream_sends_full_history(fake_llm):
    history = [
        {"role": "user", "content": "Transcripción..."},
        {"role": "assistant", "content": "## Estimación previa"},
        {"role": "user", "content": "Quita la app móvil"},
    ]
    with client.stream("POST", "/api/v1/chat/stream", json={"messages": history}) as r:
        list(r.iter_lines())
    assert fake_llm.calls[0][1] == history
