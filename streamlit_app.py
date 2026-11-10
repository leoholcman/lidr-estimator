"""Cliente Streamlit del estimador."""

import json
import os
from collections.abc import Iterator

import httpx
import streamlit as st

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT = httpx.Timeout(10.0, read=180.0)

st.set_page_config(page_title="Estimador CAG", page_icon="📐", layout="wide")


@st.cache_data(ttl=300)
def fetch_system_prompt() -> str | None:
    try:
        response = httpx.get(f"{API_URL}/api/v1/context", timeout=5.0)
        response.raise_for_status()
        return response.json()["system_prompt"]
    except httpx.HTTPError:
        return None


def stream_answer(messages: list[dict]) -> Iterator[str]:
    """Emite el texto a medida que llega y guarda las métricas al final."""
    st.session_state.last_metrics = None
    with httpx.stream(
        "POST", f"{API_URL}/api/v1/chat/stream", json={"messages": messages}, timeout=TIMEOUT
    ) as response:
        response.raise_for_status()
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


if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.last_metrics = None

# --- Sidebar: qué contexto usa el modelo y cuánto costó la última llamada ---
with st.sidebar:
    st.header("Contexto CAG")
    if st.button("🗑️ Nueva conversación", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_metrics = None
        st.rerun()

    metrics = st.session_state.last_metrics
    st.subheader("Última llamada")
    if metrics:
        col1, col2 = st.columns(2)
        col1.metric("Tokens entrada", metrics["usage"]["input_tokens"])
        col2.metric("Tokens salida", metrics["usage"]["output_tokens"])
        cost = metrics["cost_usd"]
        col1.metric("Tiempo", f"{metrics['duration_ms'] / 1000:.1f} s")
        col2.metric("Coste (¢)", f"{cost * 100:.3f}" if cost is not None else "—")
        st.caption(
            f"{metrics['provider']} · {metrics['model']}"
            + (" · desde caché" if metrics["cache_hit"] else "")
        )
    else:
        st.caption("Todavía no hay llamadas.")

    system_prompt = fetch_system_prompt()
    with st.expander("System prompt activo (incluye los ejemplos)"):
        if system_prompt:
            st.code(system_prompt, language="markdown", wrap_lines=True)
        else:
            st.warning(f"No se pudo conectar con el servicio en {API_URL}")

# --- Chat ---
st.title("📐 Estimador de proyectos")
st.caption("Pegá la transcripción de una reunión con el cliente. Después podés pedir ajustes.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Transcripción de la reunión o pedido de ajuste..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            answer = st.write_stream(stream_answer(st.session_state.messages))
        except (httpx.HTTPError, RuntimeError) as e:
            st.error(f"No se pudo generar la estimación: {e}")
            st.session_state.messages.pop()  # el usuario puede reintentar
        else:
            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.rerun()  # refresca las métricas del sidebar
