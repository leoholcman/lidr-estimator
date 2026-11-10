# Estimador CAG

Proyecto del máster de AI Engineering (LIDR). Recibe la transcripción de una reunión con un cliente y devuelve una estimación del proyecto (tareas, horas y coste) generada con un LLM.

Cada entrega está en su rama: `pre-session-02`, `pre-session-03`, etc. Cada una parte de la anterior.

## Cómo levantarlo

```bash
uv sync
cp .env.example .env   # completar las API keys
uv run uvicorn app.main:app --reload
```

Swagger queda en http://localhost:8000/docs.

## Tests

```bash
uv run pytest
uv run ruff check .
```

Ningún test llama al LLM de verdad, usan un proveedor falso.

## Sesión 03: chat en Streamlit con streaming

```bash
uv run streamlit run streamlit_app.py   # con la API levantada en otra terminal
```

- `streamlit_app.py`: chat con historial en `st.session_state`. La respuesta se ve en streaming (`st.write_stream`). En el sidebar se ve el system prompt con los ejemplos y las métricas de la última llamada.
- `POST /api/v1/chat/stream`: devuelve la respuesta en NDJSON, un fragmento por línea y al final las métricas.
- `app/services/providers.py`: una interfaz común para OpenAI y Anthropic. Si el proveedor principal falla se usa el otro (en streaming solo si falla antes del primer token).
- `app/services/cache.py`: caché exact-match en memoria. Si llega la misma conversación no se vuelve a llamar al modelo.
- Logs con structlog: un evento `llm.call` por llamada con tokens, coste y latencia.

## Sesión 02: scaffolding con FastAPI y CAG

- `POST /api/v1/estimate` recibe `{"transcription": "..."}` y devuelve la estimación con el modelo, el proveedor, los tokens y el coste.
- `GET /health`.
- El contexto es CAG: las estimaciones de ejemplo de `app/context/examples.py` van dentro del system prompt en cada llamada. No hay base de datos ni búsqueda.
- Se puede usar OpenAI o Anthropic cambiando `LLM_PROVIDER` y `LLM_MODEL` en el `.env`.

Para probar hay una transcripción en `fixtures/transcripcion_ejemplo.txt`.
