"""Métricas del stress test.

Van en un módulo aparte de `evals/metrics.py` porque evalúan otra cosa: aquellas
miran el texto de una estimación contra un caso golden; estas miran la
observación de un turno (`turn_observed`) o el snapshot de la sesión. Comparten
el mismo `MetricResult`.

Los presupuestos son contratos de diseño: se fijan antes de medir y convierten
el SLA en un test que pasa o falla.
"""

import json

from evals.metrics import MetricResult


class LatencyBudgetMetric:
    """1.0 si latency_ms <= budget_ms; 0.0 si no."""

    name = "latency_budget"

    def __init__(self, budget_ms: int):
        self.budget_ms = budget_ms

    def evaluate(self, observation: dict) -> MetricResult:
        latency = observation["latency_ms"]
        ok = latency <= self.budget_ms
        return MetricResult(self.name, float(ok), ok, f"{latency} ms (presupuesto {self.budget_ms} ms)")


class CostBudgetMetric:
    """1.0 si cost_usd <= budget_usd; 0.0 si no."""

    name = "cost_budget"

    def __init__(self, budget_usd: float):
        self.budget_usd = budget_usd

    def evaluate(self, observation: dict) -> MetricResult:
        cost = observation["cost_usd"]
        if cost is None:
            return MetricResult(self.name, 0.0, False, "coste desconocido (modelo sin precio)")
        ok = cost <= self.budget_usd
        return MetricResult(self.name, float(ok), ok, f"USD {cost:.6f} (presupuesto USD {self.budget_usd})")


LOCATIONS = ("summary", "anchors", "metadata")


def snapshot_text(snapshot: dict, location: str) -> str:
    """Texto de una de las tres memorias de la sesión (`GET /sessions/{id}`)."""
    if location == "summary":
        return snapshot.get("summary") or ""
    if location == "anchors":
        return "\n".join(snapshot.get("anchors") or [])
    if location == "metadata":
        return json.dumps(snapshot.get("project_metadata") or {}, ensure_ascii=False)
    raise ValueError(f"ubicación desconocida: {location}")


def found_in(snapshot: dict, fact: str, where=LOCATIONS) -> list[str]:
    """Ubicaciones donde aparece el hecho (match literal, sin distinguir mayúsculas)."""
    return [loc for loc in where if fact.lower() in snapshot_text(snapshot, loc).lower()]


class MemoryDriftMetric:
    """1.0 si el hecho declarado en un turno anterior sigue en el resumen, las
    anclas o el metadata de la sesión; 0.0 si no.

    Match literal a propósito: nada de embeddings ni de un LLM como juez. Si el
    resumen reescribe "30.000 EUR" como "30k", cuenta como pérdida.
    """

    name = "memory_drift"

    def __init__(self, fact: str, where: list[str] | None = None):
        self.fact = fact
        self.where = tuple(where or LOCATIONS)

    def evaluate(self, session_snapshot: dict) -> MetricResult:
        locations = found_in(session_snapshot, self.fact, self.where)
        ok = bool(locations)
        details = f"'{self.fact}' en {locations}" if ok else f"'{self.fact}' no está en {list(self.where)}"
        return MetricResult(self.name, float(ok), ok, details)
