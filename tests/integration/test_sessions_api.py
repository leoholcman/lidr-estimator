"""Tests de integración de las sesiones (pytest + httpx.AsyncClient).

El LLM es un FakeProvider determinista: responde según lo que recibe, así se
puede comprobar qué viajó en cada llamada sin gastar tokens.
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import conversation, llm_service
from tests.docs import make_pdf
from tests.fakes import FakeProvider

KNOWN_TECH = ["Stripe", "HubSpot", "Flutter", "Firebase"]


def fake_responder(system: str, messages: list[dict]) -> str:
    if system.startswith("Eres un extractor"):
        text = messages[-1]["content"]
        client_part = text.split("<mensaje_cliente>")[1]
        return json.dumps({
            "project_name": "App de reservas" if "reservas" in client_part else None,
            "assumed_team_size": 2 if "dos desarrolladores" in client_part else None,
            "mentioned_technologies": [t for t in KNOWN_TECH if t in client_part],
            "agreed_scope": None,
        })
    last_user = messages[-1]["content"]
    if "Stripe" in last_user:
        return "Estimación: 120 h. Incluye pagos con Stripe (14 h)."
    return "Estimación: 100 h. Sin pagos online."


@pytest.fixture
def fake(monkeypatch):
    fake = FakeProvider(responder=fake_responder)
    monkeypatch.setattr(llm_service, "_provider", fake)
    llm_service.cache.clear()
    conversation.store.clear()
    return fake


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def new_session(client: AsyncClient) -> str:
    response = await client.post("/api/v1/sessions")
    assert response.status_code == 201
    return response.json()["session_id"]


async def send(client: AsyncClient, session_id: str, transcript: str, files=None):
    response = await client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        data={"transcript": transcript, "project_type": "mobile_app"},
        files=files,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_metadata_updates_across_two_turns(client, fake):
    session_id = await new_session(client)

    first = await send(client, session_id, "Queremos una app de reservas para gimnasios con Firebase")
    assert first["project_metadata"]["project_name"] == "App de reservas"
    assert first["project_metadata"]["mentioned_technologies"] == ["Firebase"]

    second = await send(client, session_id, "Lo harían dos desarrolladores y cobramos con Stripe")
    metadata = second["project_metadata"]
    assert metadata["project_name"] == "App de reservas"  # no se olvidó
    assert metadata["assumed_team_size"] == 2
    assert metadata["mentioned_technologies"] == ["Firebase", "Stripe"]
    assert second["total_turns"] == 2

    # El segundo turno de estimación recibió la memoria en el system prompt
    estimation_calls = [c for c in fake.calls if not c[0].startswith("Eres un extractor")]
    assert "- Nombre del proyecto: App de reservas" in estimation_calls[1][0]

    state = (await client.get(f"/api/v1/sessions/{session_id}")).json()
    assert state["project_metadata"] == metadata


async def test_pdf_attachment_changes_the_estimation(client, fake):
    transcript = "Queremos una app de reservas para el gimnasio"

    without = await send(client, await new_session(client), transcript)

    pdf = make_pdf("Especificacion tecnica\nLos pagos se procesan con Stripe")
    with_pdf = await send(
        client,
        await new_session(client),
        transcript,
        files=[("attachments", ("specs.pdf", pdf, "application/pdf"))],
    )

    assert "Stripe" not in without["text"]
    assert "Stripe" in with_pdf["text"]  # el contenido del PDF influyó
    assert with_pdf["attachments"][0]["filename"] == "specs.pdf"
    assert "Stripe" in with_pdf["project_metadata"]["mentioned_technologies"]


async def test_history_sent_to_llm_never_exceeds_max_turns(client, fake):
    session_id = await new_session(client)
    max_turns = conversation.store.max_turns

    for i in range(8):
        await send(client, session_id, f"Turno {i}: ajustamos el alcance de la app de reservas")

    estimation_calls = [c for c in fake.calls if not c[0].startswith("Eres un extractor")]
    assert len(estimation_calls) == 8
    for _, messages in estimation_calls:
        previous_turns = (len(messages) - 1) // 2  # sin contar el mensaje nuevo
        assert previous_turns <= max_turns
    # el último turno ya no ve el primero
    assert "Turno 0" not in json.dumps(estimation_calls[-1][1])

    state = (await client.get(f"/api/v1/sessions/{session_id}")).json()
    assert state["total_turns"] == 8
    assert state["turns_in_window"] == max_turns


async def test_unknown_session_returns_404(client, fake):
    response = await client.post(
        "/api/v1/sessions/no-existe/estimate", data={"transcript": "Una app de reservas"}
    )
    assert response.status_code == 404


async def test_unsupported_attachment_returns_415(client, fake):
    session_id = await new_session(client)
    response = await client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        data={"transcript": "Una app de reservas"},
        files=[("attachments", ("foto.png", b"\x89PNG", "image/png"))],
    )
    assert response.status_code == 415
