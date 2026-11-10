import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PAYLOAD = {
    "description": "El cliente necesita una landing page con formulario y blog.",
    "project_type": "web_saas",
    "detail_level": "summary",
    "output_format": "line_items",
}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_estimate_sends_system_and_user_separately(fake_llm):
    response = client.post("/api/v1/estimate", json=PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "## Estimación: Test"
    assert body["prompt_version"] == "v1"
    system, messages = fake_llm.calls[0]
    assert "Eres un estimador experto" in system
    assert messages == [{"role": "user", "content": messages[0]["content"]}]
    assert PAYLOAD["description"] in messages[0]["content"]


def test_estimate_accepts_prompt_version(fake_llm):
    response = client.post("/api/v1/estimate?prompt_version=v2", json=PAYLOAD)
    assert response.status_code == 200
    assert response.json()["prompt_version"] == "v2"
    assert "consultor sénior" in fake_llm.calls[0][0]


def test_estimate_rejects_unknown_version(fake_llm):
    response = client.post("/api/v1/estimate?prompt_version=v9", json=PAYLOAD)
    assert response.status_code == 422


def test_estimate_validates_enums_and_length():
    assert client.post("/api/v1/estimate", json=PAYLOAD | {"project_type": "x"}).status_code == 422
    assert client.post("/api/v1/estimate", json=PAYLOAD | {"description": "corto"}).status_code == 422


def test_estimate_stream_emits_deltas_then_metrics(fake_llm):
    with client.stream("POST", "/api/v1/estimate/stream", json=PAYLOAD) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]
    deltas = [e for e in events if e["type"] == "delta"]
    assert len(deltas) > 1
    assert "".join(e["text"] for e in deltas).strip() == "## Estimación: Test"
    assert events[-1]["type"] == "done"
    assert events[-1]["prompt_version"] == "v1"


def test_prompt_preview_does_not_call_llm(fake_llm):
    response = client.post("/api/v1/prompt/preview", json=PAYLOAD)
    assert response.status_code == 200
    assert "<project_description>" in response.json()["user"]
    assert fake_llm.calls == []
