"""Cliente Streamlit del estimador."""

import json
import os
from collections.abc import Iterator

import httpx
import streamlit as st

from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType

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


@st.cache_data(ttl=300)
def fetch_versions() -> list[str]:
    try:
        response = httpx.get(f"{API_URL}/api/v1/prompt/versions", timeout=5.0)
        response.raise_for_status()
        return response.json()["versions"]
    except httpx.HTTPError:
        return ["v1"]


def stream_estimate(payload: dict, version: str) -> Iterator[str]:
    st.session_state.last_metrics = None
    with httpx.stream(
        "POST",
        f"{API_URL}/api/v1/estimate/stream",
        params={"prompt_version": version},
        json=payload,
        timeout=TIMEOUT,
    ) as response:
        if response.status_code >= 400:
            response.read()
            raise RuntimeError(response.text)
        for line in response.iter_lines():
            if not line:
                continue
            event = json.loads(line)
            if event["type"] == "delta":
                yield event["text"]
            elif event["type"] == "done":
                st.session_state.last_metrics = event
            elif event["type"] == "error":
                raise RuntimeError(event["detail"])


def fetch_preview(payload: dict, version: str) -> dict | None:
    try:
        response = httpx.post(
            f"{API_URL}/api/v1/prompt/preview",
            params={"prompt_version": version},
            json=payload,
            timeout=5.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


for key in ("last_metrics", "last_text", "last_payload", "last_version"):
    st.session_state.setdefault(key, None)

st.title("📐 Estimador de proyectos")

form_col, result_col = st.columns([2, 3], gap="large")

with form_col, st.form("estimation_form"):
    description = st.text_area(
        "Descripción del proyecto o transcripción de la reunión",
        height=220,
        max_chars=2000,
        placeholder="El cliente necesita una plataforma web para...",
    )
    project_type = st.selectbox(
        "Tipo de proyecto", list(ProjectType), format_func=PROJECT_TYPE_LABELS.get
    )
    detail_level = st.radio(
        "Nivel de detalle",
        list(DetailLevel),
        index=1,
        format_func=DETAIL_LABELS.get,
        horizontal=True,
    )
    output_format = st.radio("Formato", list(OutputFormat), format_func=FORMAT_LABELS.get)
    version = st.selectbox("Versión del prompt", fetch_versions())
    submitted = st.form_submit_button("Estimar", type="primary", use_container_width=True)

with result_col:
    if submitted:
        try:
            # Validamos en el cliente con el mismo schema que el servicio
            request = EstimationRequest(
                description=description,
                project_type=project_type,
                detail_level=detail_level,
                output_format=output_format,
            )
        except ValueError as e:
            st.error(f"Revisá el formulario: {e.errors()[0]['msg']}")
        else:
            payload = request.model_dump(mode="json", exclude_none=True)
            try:
                text = st.write_stream(stream_estimate(payload, version))
            except (httpx.HTTPError, RuntimeError) as e:
                st.error(f"No se pudo generar la estimación: {e}")
            else:
                st.session_state.last_text = text
                st.session_state.last_payload = payload
                st.session_state.last_version = version
                st.rerun()
    elif st.session_state.last_text:
        st.markdown(st.session_state.last_text)
    else:
        st.info("Completá el formulario para generar una estimación.")

with st.sidebar:
    st.header("Última llamada")
    metrics = st.session_state.last_metrics
    if metrics:
        col1, col2 = st.columns(2)
        col1.metric("Tokens entrada", metrics["usage"]["input_tokens"])
        col2.metric("Tokens salida", metrics["usage"]["output_tokens"])
        cost = metrics["cost_usd"]
        col1.metric("Tiempo", f"{metrics['duration_ms'] / 1000:.1f} s")
        col2.metric("Coste (¢)", f"{cost * 100:.3f}" if cost is not None else "—")
        st.caption(
            f"prompt {metrics['prompt_version']} · {metrics['provider']} · {metrics['model']}"
            + (" · desde caché" if metrics["cache_hit"] else "")
        )
        preview = fetch_preview(st.session_state.last_payload, st.session_state.last_version)
        if preview:
            with st.expander("Prompt enviado: system"):
                st.code(preview["system"], language="markdown", wrap_lines=True)
            with st.expander("Prompt enviado: user"):
                st.code(preview["user"], language="markdown", wrap_lines=True)
    else:
        st.caption("Todavía no hay llamadas.")
