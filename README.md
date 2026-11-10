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

## Sesión 02: scaffolding con FastAPI y CAG

- `POST /api/v1/estimate` recibe `{"transcription": "..."}` y devuelve la estimación con el modelo, el proveedor, los tokens y el coste.
- `GET /health`.
- El contexto es CAG: las estimaciones de ejemplo de `app/context/examples.py` van dentro del system prompt en cada llamada. No hay base de datos ni búsqueda.
- Se puede usar OpenAI o Anthropic cambiando `LLM_PROVIDER` y `LLM_MODEL` en el `.env`.

Para probar hay una transcripción en `fixtures/transcripcion_ejemplo.txt`.
