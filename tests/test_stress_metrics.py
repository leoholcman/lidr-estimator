from evals.stress.fixtures.build_pdfs import PLANTED, build_text
from evals.stress.metrics import CostBudgetMetric, LatencyBudgetMetric, MemoryDriftMetric
from evals.stress.scenarios import SCENARIOS

SNAPSHOT = {
    "summary": "El proyecto Nimbus suma SSO con Keycloak.",
    "anchors": ["El presupuesto queda cerrado en 30.000 EUR"],
    "project_metadata": {"project_name": "Nimbus", "mentioned_technologies": ["Metabase"]},
}


def test_latency_budget_pass_fail_and_limit():
    metric = LatencyBudgetMetric(budget_ms=4000)
    assert metric.evaluate({"latency_ms": 3999}).passed
    assert metric.evaluate({"latency_ms": 4000}).passed  # el límite cuenta como dentro
    result = metric.evaluate({"latency_ms": 4001})
    assert not result.passed and result.score == 0.0


def test_cost_budget_pass_fail_and_limit():
    metric = CostBudgetMetric(budget_usd=0.003)
    assert metric.evaluate({"cost_usd": 0.0}).passed
    assert metric.evaluate({"cost_usd": 0.003}).passed
    assert not metric.evaluate({"cost_usd": 0.0031}).passed
    assert not metric.evaluate({"cost_usd": None}).passed  # sin precio no se puede aprobar


def test_memory_drift_finds_fact_in_each_location():
    assert MemoryDriftMetric("keycloak").evaluate(SNAPSHOT).passed  # resumen, sin distinguir mayúsculas
    assert MemoryDriftMetric("30.000 EUR").evaluate(SNAPSHOT).passed  # ancla
    assert MemoryDriftMetric("Metabase").evaluate(SNAPSHOT).passed  # metadata
    assert "anchors" in MemoryDriftMetric("30.000 EUR").evaluate(SNAPSHOT).details


def test_memory_drift_fails_when_fact_is_gone_or_reworded():
    assert not MemoryDriftMetric("Flutter").evaluate(SNAPSHOT).passed
    assert not MemoryDriftMetric("30k").evaluate(SNAPSHOT).passed  # match literal
    assert not MemoryDriftMetric("Keycloak", where=["anchors"]).evaluate(SNAPSHOT).passed
    assert not MemoryDriftMetric("Nimbus").evaluate({}).passed  # sesión vacía


def test_scenarios_have_20_turns_and_literal_facts():
    for scenario in SCENARIOS.values():
        assert [t.turn_index for t in scenario.turns] == list(range(1, 21))
        for turn in scenario.turns:
            if turn.fact:
                assert turn.fact in turn.transcript  # el hecho está literal en el mensaje


def test_pdf_text_is_deterministic_and_has_planted_facts():
    text = build_text(20_000)
    assert text == build_text(20_000)
    assert 20_000 <= len(text) < 20_200
    for _, _, token in PLANTED:
        assert token in text
