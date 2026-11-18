"""Métricas deterministas sobre una estimación.

Ninguna usa un LLM para juzgar: corren gratis y dicen exactamente por qué falla
un caso. Todas devuelven un `MetricResult`.
"""

import re
from dataclasses import dataclass


@dataclass
class MetricResult:
    name: str
    score: float
    passed: bool
    details: str


_TOTAL_HOURS = re.compile(r"total[^\n]{0,40}?(\d[\d.]*)\s*(horas|h)\b", re.IGNORECASE)


def parse_total_hours(text: str) -> int | None:
    match = _TOTAL_HOURS.search(text)
    return int(match.group(1).replace(".", "")) if match else None


class ContentRecallMetric:
    """Fracción de palabras clave esperadas que aparecen en la estimación."""

    name = "content_recall"

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    def evaluate(self, case: dict, text: str) -> MetricResult:
        expected = case.get("expected_keywords", [])
        found = [k for k in expected if k.lower() in text.lower()]
        score = len(found) / len(expected) if expected else 1.0
        missing = sorted(set(expected) - set(found))
        return MetricResult(self.name, score, score >= self.threshold, f"faltan: {missing}" if missing else "ok")


class HoursBoundsMetric:
    """El total de horas existe y cae dentro del rango razonable del caso."""

    name = "hours_bounds"

    def evaluate(self, case: dict, text: str) -> MetricResult:
        hours = parse_total_hours(text)
        if hours is None:
            return MetricResult(self.name, 0.0, False, "no se encontró el total de horas")
        low, high = case["expected_hours_range"]
        ok = low <= hours <= high
        return MetricResult(self.name, float(ok), ok, f"{hours} h (rango {low}-{high})")


DEFAULT_METRICS = (ContentRecallMetric(), HoursBoundsMetric())


def run_all_metrics(case: dict, text: str, metrics=DEFAULT_METRICS) -> list[MetricResult]:
    return [metric.evaluate(case, text) for metric in metrics]
