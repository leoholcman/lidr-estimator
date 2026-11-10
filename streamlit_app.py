"""Cliente Streamlit del estimador."""

import os

import httpx
import streamlit as st

from app.schemas import DetailLevel, OutputFormat, ProjectType

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT = httpx.Timeout(10.0, read=180.0)

PROJECT_TYPE_LABELS = {
    ProjectType.MOBILE_APP: "📱 App móvil",
    ProjectType.WEB_SAAS: "🌐 Web / SaaS",
    ProjectType.INTERNAL_TOOL: "🛠️ Herramienta interna",
    ProjectType.DATA_PIPELINE: "🔀 Pipeline de datos",
}
DETAIL_LABELS = {
    DetailLevel.SUMMARY: "Resumen",
    DetailLevel.MEDIUM: "Medio",
    DetailLevel.DETAILED: "Detallado",
}
FORMAT_LABELS = {
    OutputFormat.PHASES_TABLE: "Tabla por fases",
    OutputFormat.LINE_ITEMS: "Lista de tareas",
    OutputFormat.NARRATIVE: "Narrativo (email al cliente)",
}

st.set_page_config(page_title="Estimador", page_icon="📐", layout="wide")


def api_error(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text


def new_session() -> None:
    response = httpx.post(f"{API_URL}/api/v1/sessions", timeout=10.0)
    response.raise_for_status()
    st.session_state.session_id = response.json()["session_id"]
    st.session_state.turns = []  # lo que se muestra en pantalla
    st.session_state.state = None  # último SessionState del servicio
    st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1


def send_turn(transcript: str, files, params: dict) -> dict:
    response = httpx.post(
        f"{API_URL}/api/v1/sessions/{st.session_state.session_id}/estimate",
        data={"transcript": transcript, **params},
        files=[("attachments", (f.name, f.getvalue(), f.type)) for f in files],
        timeout=TIMEOUT,
    )
    if response.status_code == 404:
        raise LookupError("La sesión ya no existe en el servicio (¿se reinició?).")
    if response.status_code >= 400:
        raise RuntimeError(api_error(response))
    return response.json()


if "session_id" not in st.session_state:
    try:
        new_session()
    except httpx.HTTPError as e:
        st.error(f"No se pudo conectar con el servicio IA en {API_URL}: {e}")
        st.stop()

# --- Sidebar: memoria del proyecto y métricas ---
with st.sidebar:
    if st.button("🆕 Nueva conversación", use_container_width=True):
        new_session()
        st.rerun()
    st.caption(f"Sesión `{st.session_state.session_id[:8]}`")

    state = st.session_state.state
    st.header("🧠 project_metadata")
    st.caption("Hechos del proyecto que se inyectan en el system prompt en cada turno.")
    if state:
        st.json(state["project_metadata"])
        st.caption(
            f"Historial: {state['turns_in_window']}/{state['max_turns']} turnos en la ventana "
            f"· {state['total_turns']} en total"
        )
        st.header("Última llamada")
        col1, col2 = st.columns(2)
        col1.metric("Tokens entrada", state["usage"]["input_tokens"])
        col2.metric("Tokens salida", state["usage"]["output_tokens"])
        cost = state["cost_usd"]
        col1.metric("Tiempo", f"{state['duration_ms'] / 1000:.1f} s")
        col2.metric("Coste (¢)", f"{cost * 100:.3f}" if cost is not None else "—")
        st.caption(f"prompt {state['prompt_version']} · {state['provider']} · {state['model']}")
    else:
        st.info("Vacío hasta el primer turno.")

# --- Conversación ---
st.title("📐 Estimador de proyectos")
st.caption(
    "Pegá la transcripción y adjuntá documentación (PDF, Word). "
    "En los turnos siguientes podés refinar el alcance: el estimador recuerda el proyecto."
)

for turn in st.session_state.turns:
    with st.chat_message("user"):
        st.markdown(turn["transcript"])
        if turn["attachments"]:
            st.caption("📎 " + ", ".join(turn["attachments"]))
    with st.chat_message("assistant"):
        st.markdown(turn["text"])

with st.form("turn_form", clear_on_submit=True):
    transcript = st.text_area(
        "Transcripción o mensaje",
        height=150,
        placeholder="En la reunión el cliente explicó que necesita...",
    )
    files = st.file_uploader(
        "Adjuntos",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.uploader_key}",
    )
    col1, col2, col3 = st.columns(3)
    project_type = col1.selectbox(
        "Tipo de proyecto", list(ProjectType), format_func=PROJECT_TYPE_LABELS.get
    )
    detail_level = col2.selectbox(
        "Nivel de detalle", list(DetailLevel), index=1, format_func=DETAIL_LABELS.get
    )
    output_format = col3.selectbox("Formato", list(OutputFormat), format_func=FORMAT_LABELS.get)
    submitted = st.form_submit_button("Enviar", type="primary", use_container_width=True)

if submitted:
    if len(transcript.strip()) < 10:
        st.warning("Escribí al menos una frase.")
    else:
        params = {
            "project_type": project_type.value,
            "detail_level": detail_level.value,
            "output_format": output_format.value,
        }
        with st.spinner("Estimando y actualizando la memoria del proyecto..."):
            try:
                result = send_turn(transcript, files or [], params)
            except LookupError as e:
                new_session()
                st.warning(f"{e} Se abrió una conversación nueva: volvé a enviar el mensaje.")
            except (httpx.HTTPError, RuntimeError) as e:
                st.error(f"No se pudo generar la estimación: {e}")
            else:
                st.session_state.turns.append({
                    "transcript": transcript,
                    "attachments": [a["filename"] for a in result["attachments"]],
                    "text": result["text"],
                })
                st.session_state.state = result
                st.rerun()
