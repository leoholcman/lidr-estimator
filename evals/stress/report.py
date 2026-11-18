"""Arma las tablas del reporte a partir del CSV del stress test.

    uv run python -m evals.stress.report evals/stress/results.csv

Imprime Markdown. La lectura de los números (los párrafos de REPORT.md) se
escribe a mano.
"""

import csv
import sys
from collections import defaultdict
from statistics import mean

from evals.stress.scenarios import CHECKPOINTS

TOKEN_BINS = ((0, 3000), (3000, 4000), (4000, 5000), (5000, 6000), (6000, 8000), (8000, 10**9))
NUMERIC = (
    "repeat", "attachment_kb", "turn_index", "attachments_total_chars", "messages_in_window",
    "anchors_count", "summary_chars", "tokens_in", "tokens_out", "cost_usd", "latency_ms",
    "facts_declared", "facts_visible", "facts_in_memory", "in_summary", "in_anchors",
    "in_metadata", "stale_present", "project_name_ok", "attachment_recall",
    "attachment_truncated", "latency_budget", "cost_budget", "memory_drift",
)


def load(path: str) -> list[dict]:
    rows = []
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            for key in NUMERIC:
                row[key] = float(row[key]) if row[key] != "" else None
            rows.append(row)
    return rows


def percentile(values: list[float], p: float) -> float:
    """Percentil por rango más cercano (suficiente para muestras chicas)."""
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(p / 100 * len(ordered) + 0.5) - 1))
    return ordered[index]


def table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def cold(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["cache_hit_kind"] == "none"]


def summary_table(rows: list[dict]) -> str:
    groups = defaultdict(list)
    for r in rows:
        groups[(r["scenario"], int(r["attachment_kb"]))].append(r)
    out = []
    for (scenario, size), group in groups.items():
        misses = cold(group) or group
        latencies = [r["latency_ms"] for r in misses]
        recalls = [r["memory_drift"] if r["block"] == "memory" else r["attachment_recall"] for r in group]
        recalls = [x for x in recalls if x is not None]
        out.append([
            scenario, size, len(group),
            f"{percentile(latencies, 50):.0f}", f"{percentile(latencies, 95):.0f}",
            f"{sum(r['cost_usd'] for r in group):.4f}",
            pct(mean(r["cache_hit_kind"] == "exact" for r in group)),
            pct(mean(r["cache_hit_kind"] == "semantic" for r in group)),
            f"{mean(recalls):.2f}" if recalls else "n/a",
        ])
    return table(
        ["Escenario", "Adjunto (KB)", "Turnos", "P50 latencia (ms)", "P95 latencia (ms)",
         "Coste total (USD)", "Caché exacta", "Caché semántica", "Recall medio"],
        out,
    )


def latency_vs_tokens(rows: list[dict]) -> str:
    out = []
    for low, high in TOKEN_BINS:
        group = [r for r in cold(rows) if low <= r["tokens_in"] < high]
        if not group:
            continue
        label = f"{low // 1000}k a {high // 1000}k" if high < 10**9 else f"más de {low // 1000}k"
        latencies = [r["latency_ms"] for r in group]
        out.append([label, len(group), f"{mean(latencies):.0f}", f"{percentile(latencies, 95):.0f}",
                    f"{mean(r['tokens_out'] for r in group):.0f}"])
    return table(["tokens_in del turno", "Turnos", "Latencia media (ms)", "P95 (ms)", "tokens_out medio"], out)


def cost_vs_turn(rows: list[dict]) -> str:
    out = []
    memory = [r for r in rows if r["block"] == "memory"]
    for scenario in dict.fromkeys(r["scenario"] for r in memory):
        by_repeat = defaultdict(list)
        for r in memory:
            if r["scenario"] == scenario:
                by_repeat[r["repeat"]].append(r)
        first_turn = mean(turns[0]["cost_usd"] for turns in by_repeat.values() if turns[0]["cost_usd"])
        for n in CHECKPOINTS:
            at_n = [t for turns in by_repeat.values() for t in turns if t["turn_index"] == n]
            if not at_n:
                continue
            accumulated = mean(
                sum(t["cost_usd"] for t in turns if t["turn_index"] <= n) for turns in by_repeat.values()
            )
            turn_cost = mean(t["cost_usd"] for t in at_n)
            out.append([scenario, n, f"{mean(t['tokens_in'] for t in at_n):.0f}", f"{turn_cost:.5f}",
                        f"x{turn_cost / first_turn:.1f}" if first_turn else "n/a", f"{accumulated:.4f}"])
    return table(
        ["Escenario", "Turno", "tokens_in", "Coste del turno (USD)", "vs turno 1", "Coste acumulado (USD)"],
        out,
    )


def recall_vs_n(rows: list[dict]) -> str:
    out = []
    memory = [r for r in rows if r["block"] == "memory"]
    for scenario in dict.fromkeys(r["scenario"] for r in memory):
        for n in CHECKPOINTS:
            at_n = [r for r in memory if r["scenario"] == scenario and r["turn_index"] == n]
            if not at_n:
                continue
            declared = mean(r["facts_declared"] for r in at_n)
            out.append([
                scenario, n, f"{declared:.0f}",
                f"{mean(r['memory_drift'] for r in at_n):.2f}",
                f"{mean(r['facts_in_memory'] / r['facts_declared'] for r in at_n):.2f}",
                f"{mean(r['in_summary'] for r in at_n):.1f}",
                f"{mean(r['in_anchors'] for r in at_n):.1f}",
                f"{mean(r['in_metadata'] for r in at_n):.1f}",
                f"{mean(r['stale_present'] for r in at_n):.1f}",
                pct(mean(r["project_name_ok"] for r in at_n)),
            ])
    return table(
        ["Escenario", "N (turnos)", "Hechos declarados", "Recall visible", "Recall solo memoria",
         "En resumen", "En anclas", "En metadata", "Hechos viejos presentes", "project_name ok"],
        out,
    )


def attachments_table(rows: list[dict]) -> str:
    out = []
    attachment = [r for r in rows if r["block"] == "attachment"]
    keys = dict.fromkeys((r["scenario"], int(r["attachment_kb"])) for r in attachment)
    for scenario, size in keys:
        group = [r for r in attachment if r["scenario"] == scenario and int(r["attachment_kb"]) == size]
        first = cold(group)[0] if cold(group) else group[0]  # sin fila en frío: se ve la de caché
        recalls = [r["attachment_recall"] for r in group if r["attachment_recall"] is not None]
        out.append([
            scenario, size, f"{first['attachments_total_chars']:.0f}", f"{first['tokens_in']:.0f}",
            f"{first['latency_ms']:.0f}", f"{first['cost_usd']:.5f}",
            f"{mean(recalls):.2f}" if recalls else "n/a",
            "sí" if any(r["attachment_truncated"] for r in group) else "no",
            ", ".join(r["cache_hit_kind"] for r in group),
        ])
    return table(
        ["Corrida", "Adjunto (KB)", "Caracteres al prompt", "tokens_in (en frío)", "Latencia en frío (ms)",
         "Coste en frío (USD)", "Recall del adjunto", "Truncado", "Caché por repetición"],
        out,
    )


def budgets_table(rows: list[dict]) -> str:
    out = []
    for scenario in dict.fromkeys(r["scenario"] for r in rows):
        group = cold([r for r in rows if r["scenario"] == scenario])
        if not group:
            continue
        late = [int(r["turn_index"]) for r in group if not r["latency_budget"]]
        out.append([
            scenario, len(group), pct(mean(r["latency_budget"] for r in group)),
            pct(mean(r["cost_budget"] for r in group)),
            min(late) if late else "ninguno",
        ])
    return table(
        ["Escenario", "Turnos en frío", "Dentro de latencia", "Dentro de coste", "Primer turno fuera de latencia"],
        out,
    )


def main() -> None:
    rows = load(sys.argv[1] if len(sys.argv) > 1 else "evals/stress/results.csv")
    sections = [
        ("Tabla resumen", summary_table),
        ("Curva 1: latencia vs tokens", latency_vs_tokens),
        ("Curva 2: coste acumulado vs turno", cost_vs_turn),
        ("Curva 3: recall vs N", recall_vs_n),
        ("Adjuntos", attachments_table),
        ("Presupuestos", budgets_table),
    ]
    print(f"Filas: {len(rows)}\n")
    for title, build in sections:
        print(f"### {title}\n\n{build(rows)}\n")


if __name__ == "__main__":
    main()
