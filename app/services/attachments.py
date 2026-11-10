"""Extrae el texto de los adjuntos (PDF, DOCX, TXT) para sumarlo al prompt."""

import io
from dataclasses import dataclass

from docx import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CHARS_PER_FILE = 20_000  # ~5k tokens: acota el coste por adjunto
SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


class AttachmentError(ValueError):
    """Adjunto inválido: la API lo traduce a un 4xx."""


@dataclass
class ExtractedAttachment:
    filename: str
    text: str
    truncated: bool


def _extract_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except PdfReadError as e:
        raise AttachmentError(f"PDF ilegible: {e}") from e


def _extract_docx(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
    except Exception as e:  # python-docx lanza varios tipos según el fallo
        raise AttachmentError(f"Documento Word ilegible: {e}") from e
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def extract_text(filename: str, data: bytes) -> ExtractedAttachment:
    name = filename.lower()
    if not name.endswith(SUPPORTED_EXTENSIONS):
        raise AttachmentError(
            f"Formato no soportado: {filename}. Se aceptan {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    if len(data) > MAX_FILE_BYTES:
        raise AttachmentError(f"{filename} supera {MAX_FILE_BYTES // 1024 // 1024} MB")

    if name.endswith(".pdf"):
        text = _extract_pdf(data)
    elif name.endswith(".docx"):
        text = _extract_docx(data)
    else:
        text = data.decode("utf-8", errors="replace")

    text = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    if not text:
        raise AttachmentError(f"{filename} no tiene texto extraíble (¿es un escaneo?)")
    truncated = len(text) > MAX_CHARS_PER_FILE
    return ExtractedAttachment(filename, text[:MAX_CHARS_PER_FILE], truncated)
