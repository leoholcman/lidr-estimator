import pytest

from app.prompts.loader import render_session_prompt
from app.schemas import DetailLevel, OutputFormat, ProjectType
from app.services.attachments import AttachmentError, ExtractedAttachment, extract_text
from app.services.conversation import _parse_metadata
from app.sessions import ConversationHistory, ProjectMetadata
from tests.docs import make_docx, make_pdf


def test_history_keeps_last_n_turns_and_system_first():
    history = ConversationHistory(max_turns=2)
    for i in range(5):
        history.add_turn(f"u{i}", f"a{i}")
    messages = history.to_messages_list("SYSTEM", pending_user="nuevo")
    assert messages[0] == {"role": "system", "content": "SYSTEM"}
    assert [m["content"] for m in messages[1:]] == ["u3", "a3", "u4", "a4", "nuevo"]
    assert history.total_turns == 5 and len(history) == 2


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
