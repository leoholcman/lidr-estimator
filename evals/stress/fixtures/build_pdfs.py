"""Genera los PDFs sintéticos del stress test.

    uv run python -m evals.stress.fixtures.build_pdfs

Los tamaños son de TEXTO (5 KB = 5.000 caracteres), que es lo que le importa al
prompt; el archivo pesa algo distinto por la compresión del PDF. El contenido es
determinista (sin aleatoriedad), así que los PDFs no se commitean: se regeneran.

En cada documento se plantan tres requisitos reconocibles, al 5%, 50% y 95% del
texto. Sirven para medir qué parte del adjunto llega a la respuesta.
"""

from pathlib import Path

from fpdf import FPDF

FIXTURES = Path(__file__).parent
SIZES_KB = (5, 20, 50, 100)

# (posición relativa, texto plantado, token que se busca en la respuesta)
PLANTED = (
    (0.05, "Requisito prioritario: integracion con SAP Business One para sincronizar clientes.", "SAP Business One"),
    (0.50, "Requisito prioritario: exportacion de remesas bancarias en formato SEPA.", "SEPA"),
    (0.95, "Requisito prioritario: firma digital de documentos con certificados FNMT.", "FNMT"),
)

_MODULES = ("clientes", "pedidos", "facturas", "stock", "usuarios", "reportes", "pagos", "envios")
_ACTIONS = ("listar", "filtrar", "editar", "exportar", "archivar", "duplicar", "aprobar", "auditar")
_DETAILS = (
    "con paginacion y orden por columna",
    "respetando los permisos del rol",
    "dejando registro en el historial",
    "con validacion de campos obligatorios",
    "y con confirmacion antes de guardar",
)


def filler_line(i: int) -> str:
    module = _MODULES[i % len(_MODULES)]
    action = _ACTIONS[(i // len(_MODULES)) % len(_ACTIONS)]
    detail = _DETAILS[i % len(_DETAILS)]
    return f"{i + 1}. El modulo de {module} debe permitir {action} registros {detail}."


def build_text(target_chars: int) -> str:
    lines = ["Especificacion funcional del sistema (documento de trabajo)."]
    size = len(lines[0])
    i = 0
    pending = list(PLANTED)
    while size < target_chars:
        if pending and size >= pending[0][0] * target_chars:
            line = pending.pop(0)[1]
        else:
            line = filler_line(i)
            i += 1
        lines.append(line)
        size += len(line) + 1
    return "\n".join(lines)


def pdf_path(size_kb: int) -> Path:
    return FIXTURES / f"attach_{size_kb}kb.pdf"


def build_pdf(size_kb: int) -> Path:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in build_text(size_kb * 1000).split("\n"):
        pdf.multi_cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    path = pdf_path(size_kb)
    pdf.output(str(path))
    return path


def build_all() -> list[Path]:
    return [build_pdf(size) for size in SIZES_KB]


if __name__ == "__main__":
    for path in build_all():
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KB en disco")
