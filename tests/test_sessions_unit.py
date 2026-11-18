import pytest

from app.compression import anchor_rules, compress
from app.prompts.loader import render_session_prompt
from app.schemas import DetailLevel, OutputFormat, ProjectType
from app.services.attachments import AttachmentError, ExtractedAttachment, extract_text
from app.services.conversation import _parse_metadata
from app.services.providers import LLMResult
from app.services.semantic_cache import SemanticCache
from app.sessions import ConversationHistory, ProjectMetadata
from app.tier import Tier, resolve_tier
from tests.docs import make_docx, make_pdf


def test_history_overflow_returns_oldest_turns():
    history = ConversationHistory(max_turns=2)
    for i in range(5):
        history.add_turn(f"t{i}", f"u{i}", f"a{i}")
    evicted = history.overflow()
    assert [t.transcript for t in evicted] == ["t0", "t1", "t2"]
    messages = history.to_messages_list("SYSTEM", pending_user="nuevo")
    assert messages[0] == {"role": "system", "content": "SYSTEM"}
    assert [m["content"] for m in messages[1:]] == ["u3", "a3", "u4", "a4", "nuevo"]
    assert history.total_turns == 5 and len(history) == 2


async def test_compress_sends_anchors_and_summary_to_different_places():
    history = ConversationHistory(max_turns=1)
    history.add_turn("El alcance queda cerrado, firmamos el contrato ayer", "u0", "a0")
    history.add_turn("Agregamos un blog", "u1", "a1")
    history.add_turn("Y un buscador", "u2", "a2")
    seen = []

    async def summarize(previous, evicted):
        seen.append([t.transcript for t in evicted])
        return "resumen"

    await compress(history, summarize)
    assert history.anchors == ["El alcance queda cerrado, firmamos el contrato ayer"]
    assert seen == [["Agregamos un blog"]]
    assert history.summary == "resumen"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("El presupuesto está aprobado: 80.000 EUR", True),
        ("Tenemos que cumplir GDPR", True),
        ("La fecha límite es el 15 de marzo", True),
        ("Queremos una app con login y un panel", False),
        ("¿Cuánto saldría agregar pagos?", False),
    ],
)
def test_anchor_rules(text, expected):
    assert bool(anchor_rules(text)) is expected


def test_tier_rules_in_order_of_precedence():
    empty = ProjectMetadata()
    assert resolve_tier("Firmamos un NDA y usamos Docker y Kafka", empty) == (Tier.EXECUTIVE, "nda_detected")
    assert resolve_tier("Corre en Docker con Kubernetes", empty) == (Tier.DEVELOPER, "technical_audience")
    assert resolve_tier("Corre en Docker", empty) == (Tier.DEFAULT, "default")
    small = ProjectMetadata(assumed_team_size=2)
    assert resolve_tier("Una app simple", small) == (Tier.PM, "small_team_pm")
    assert resolve_tier("Una app simple", small, Tier.EXECUTIVE) == (Tier.EXECUTIVE, "explicit_override")


async def test_semantic_cache_hits_only_same_bucket_and_similar_text():
    vectors = {"app de reservas": [1.0, 0.0], "app de reservas!": [0.99, 0.05], "pipeline de datos": [0.0, 1.0]}

    async def embedder(text):
        return vectors[text]

    cache = SemanticCache(embedder, threshold=0.92)
    result = LLMResult("estimación", "m", "p", 10, 0, 5)
    _, vector = await cache.lookup("v1:web", "app de reservas")
    cache.store("v1:web", vector, result)

    hit, _ = await cache.lookup("v1:web", "app de reservas!")
    assert hit is not None and hit.cache_hit and hit.cost_usd == 0.0
    assert (await cache.lookup("v1:web", "pipeline de datos"))[0] is None
    assert (await cache.lookup("v1:mobile", "app de reservas!"))[0] is None


def test_metadata_merge_keeps_known_facts_and_accumulates_technologies():
    current = ProjectMetadata(project_name="Gym App", mentioned_technologies=["Stripe"])
    update = ProjectMetadata(assumed_team_size=2, mentioned_technologies=["stripe", "Flutter"])
    merged = current.merge(update)
    assert merged.project_name == "Gym App"
    assert merged.assumed_team_size == 2
    assert merged.mentioned_technologies == ["Stripe", "Flutter"]


def test_parse_metadata_accepts_fenced_json():
    text = '```json\n{"project_name": "X", "assumed_team_size": null, ' \
        '"mentioned_technologies": ["React"], "agreed_scope": null}\n```'
    assert _parse_metadata(text).mentioned_technologies == ["React"]


def _render(metadata: ProjectMetadata, attachments=()):
    return render_session_prompt(
        transcript="Queremos una app de reservas",
        attachments=list(attachments),
        project_type=ProjectType.MOBILE_APP,
        detail_level=DetailLevel.MEDIUM,
        output_format=OutputFormat.LINE_ITEMS,
        project_metadata=metadata,
    )


def test_project_metadata_block_empty_on_first_turn_and_filled_later():
    system, _ = _render(ProjectMetadata())
    assert "<project_metadata>\n</project_metadata>" in system
    system, _ = _render(ProjectMetadata(project_name="Gym App", mentioned_technologies=["Stripe"]))
    assert "- Nombre del proyecto: Gym App" in system
    assert "- Tecnologías mencionadas: Stripe" in system


def test_attachments_are_concatenated_with_separator():
    attachment = ExtractedAttachment("specs.pdf", "Pagos con Stripe", truncated=False)
    _, user = _render(ProjectMetadata(), [attachment])
    assert "--- attachment: specs.pdf ---\nPagos con Stripe" in user


def test_extract_text_from_pdf_and_docx():
    assert "Stripe" in extract_text("a.pdf", make_pdf("Integrar pagos con Stripe")).text
    assert "Flutter" in extract_text("a.docx", make_docx(["App en Flutter"])).text


def test_extract_rejects_unsupported_format():
    with pytest.raises(AttachmentError):
        extract_text("foto.png", b"\x89PNG")
