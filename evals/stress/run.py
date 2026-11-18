"""Corre el stress test y vuelca una fila por turno a un CSV.

    uv run python -m evals.stress.run --http http://localhost:8000 \\
        --scenarios growing,pivot,contradiction \\
        --attachment-sizes 0,5,20,50,100 \\
        --repeats 3 \\
        --output evals/stress/results.csv

Dos bloques:

- **Memoria**: cada escenario se conversa entero (20 turnos), sin adjunto, una
  vez por repetición. Cada repetición lleva una marca distinta en el texto para
  que la caché exacta no conteste por ella y la medición sea en frío.
- **Adjuntos**: un único turno con el mismo texto y un PDF de cada tamaño. Acá
  las repeticiones son idénticas a propósito: la primera mide en frío y las
  siguientes muestran lo que ahorra la caché.

Sin `--http` usa la app en proceso (también llama al LLM de verdad).
"""

import argparse
import asyncio
import csv
from pathlib import Path

import httpx

from evals.stress.fixtures.build_pdfs import PLANTED, SIZES_KB, build_pdf, pdf_path
from evals.stress.metrics import (
    LOCATIONS,
    CostBudgetMetric,
    LatencyBudgetMetric,
    MemoryDriftMetric,
    found_in,
)
from evals.stress.scenarios import SCENARIOS, Scenario

API = "/api/v1"
ATTACHMENT_TRANSCRIPT = (
    "Reunión con una distribuidora mayorista. Quieren reemplazar su sistema de gestión "
    "por una plataforma web. Adjunto la especificación funcional que nos pasaron."
)

# Presupuestos por turno, fijados antes de medir.
LATENCY_BUDGET_MS = 10_000
COST_BUDGET_USD = 0.003

OBSERVED = [
    "turn_index", "session_id", "enriched_transcript_chars", "attachments_total_chars",
    "messages_in_window", "anchors_count", "summary_chars", "tokens_in", "tokens_out",
    "cost_usd", "latency_ms", "cache_hit_kind", "last_resolved_tier",
]
COLUMNS = [
    "block", "scenario", "repeat", "attachment_kb", *OBSERVED,
    "facts_declared", "facts_visible", "facts_in_memory",
    "in_summary", "in_anchors", "in_metadata", "stale_present", "project_name_ok",
    "attachment_recall", "attachment_truncated",
    "latency_budget", "cost_budget", "memory_drift",
]


def make_client(http: str | None) -> httpx.AsyncClient:
    if http:
        return httpx.AsyncClient(base_url=http, timeout=300)
    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stress", timeout=300)


async def send_turn(client, session_id: str, transcript: str, project_type: str, pdf: Path | None):
    files = [("attachments", (pdf.name, pdf.read_bytes(), "application/pdf"))] if pdf else None
    response = await client.post(
        f"{API}/sessions/{session_id}/estimate",
        data={"transcript": transcript, "project_type": project_type, "detail_level": "summary"},
        files=files,
    )
    response.raise_for_status()
    # El turn_observed se lee del snapshot (viene embebido en la respuesta y en
    # GET /sessions/{id}) en vez de parsear los logs del servicio.
    return response.json()


def budget_columns(observation: dict) -> dict:
    return {
        "latency_budget": LatencyBudgetMetric(LATENCY_BUDGET_MS).evaluate(observation).score,
        "cost_budget": CostBudgetMetric(COST_BUDGET_USD).evaluate(observation).score,
    }


def memory_columns(scenario: Scenario, turn_index: int, snapshot: dict) -> dict:
    """Qué recuerda la sesión, en el turno N, de los hechos declarados antes."""
    facts = [(t.turn_index, t.fact) for t in scenario.turns if t.fact and t.turn_index <= turn_index]
    window_start = turn_index - snapshot["max_turns"]  # turnos > window_start siguen textuales
    in_memory = [fact for _, fact in facts if MemoryDriftMetric(fact).evaluate(snapshot).passed]
    visible = [fact for k, fact in facts if k > window_start or fact in in_memory]
    per_location = {loc: sum(bool(found_in(snapshot, fact, [loc])) for _, fact in facts) for loc in LOCATIONS}
    stale = [fact for since, fact in scenario.stale if turn_index >= since and found_in(snapshot, fact)]
    name = (snapshot["project_metadata"].get("project_name") or "").lower()
    return {
        "facts_declared": len(facts),
        "facts_visible": len(visible),
        "facts_in_memory": len(in_memory),
        "in_summary": per_location["summary"],
        "in_anchors": per_location["anchors"],
        "in_metadata": per_location["metadata"],
        "stale_present": len(stale),
        "project_name_ok": int(scenario.project_name.lower() in name),
        # recall del fact-tracker: fracción de hechos que el modelo todavía puede ver
        "memory_drift": round(len(visible) / len(facts), 3) if facts else 1.0,
    }


async def run_scenario(client, scenario: Scenario, repeat: int, turns: int, write) -> None:
    session_id = (await client.post(f"{API}/sessions")).json()["session_id"]
    for turn in scenario.turns[:turns]:
        transcript = f"{turn.transcript} (Ref. interna de la reunión: r{repeat}.)"
        snapshot = await send_turn(client, session_id, transcript, scenario.project_type, None)
        observation = snapshot["last_turn"]
        write({
            "block": "memory", "scenario": scenario.name, "repeat": repeat, "attachment_kb": 0,
            **{k: observation[k] for k in OBSERVED},
            **memory_columns(scenario, turn.turn_index, snapshot),
            **budget_columns(observation),
        })
        print(f"  {scenario.name} r{repeat} turno {turn.turn_index:>2}: "
              f"{observation['latency_ms']:>6} ms  {observation['tokens_in']:>6} tok  {observation['cache_hit_kind']}")


async def run_attachments(client, sizes: list[int], repeats: int, write) -> None:
    for size in sizes:
        pdf = None
        if size:
            pdf = pdf_path(size) if pdf_path(size).exists() else build_pdf(size)
        for repeat in range(1, repeats + 1):
            session_id = (await client.post(f"{API}/sessions")).json()["session_id"]
            snapshot = await send_turn(client, session_id, ATTACHMENT_TRANSCRIPT, "web_saas", pdf)
            observation = snapshot["last_turn"]
            found = [token for _, _, token in PLANTED if token.lower() in snapshot["text"].lower()]
            write({
                "block": "attachment", "scenario": "attachment", "repeat": repeat, "attachment_kb": size,
                **{k: observation[k] for k in OBSERVED},
                "attachment_recall": round(len(found) / len(PLANTED), 3) if size else "",
                "attachment_truncated": int(any(a["truncated"] for a in snapshot["attachments"])),
                **budget_columns(observation),
            })
            print(f"  adjunto {size:>3} KB r{repeat}: {observation['latency_ms']:>6} ms  "
                  f"{observation['tokens_in']:>6} tok  {observation['cache_hit_kind']}  recall={found}")


async def run_repeats(client, scenario: Scenario, repeats: int, turns: int, write) -> None:
    # Las repeticiones de un escenario van en serie (la 2 tiene que encontrar en
    # caché lo que dejó la 1); los escenarios entre sí van en paralelo.
    for repeat in range(1, repeats + 1):
        await run_scenario(client, scenario, repeat, turns, write)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--http", help="URL del servicio; si falta se usa la app en proceso")
    parser.add_argument("--scenarios", default="growing,pivot,contradiction")
    parser.add_argument("--attachment-sizes", default="0,5,20,50,100")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--turns", type=int, default=20, help="turnos por escenario (máx. 20)")
    parser.add_argument("--output", default="evals/stress/results.csv")
    args = parser.parse_args()

    scenarios = [SCENARIOS[name] for name in args.scenarios.split(",") if name]
    sizes = [int(s) for s in args.attachment_sizes.split(",") if s != ""]
    unknown = [s for s in sizes if s and s not in SIZES_KB]
    if unknown:
        raise SystemExit(f"Tamaños sin fixture: {unknown}. Disponibles: {SIZES_KB}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:  # noqa: ASYNC230
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, restval="")

        def write(row: dict) -> None:
            writer.writerow(row)
            handle.flush()  # si se corta a mitad, lo medido queda

        writer.writeheader()
        async with make_client(args.http) as client:
            await asyncio.gather(
                *(run_repeats(client, s, args.repeats, args.turns, write) for s in scenarios),
                run_attachments(client, sizes, args.repeats, write),
            )
    print(f"\nListo: {output}")


if __name__ == "__main__":
    asyncio.run(main())
