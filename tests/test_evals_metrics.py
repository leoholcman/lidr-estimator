from evals.metrics import ContentRecallMetric, HoursBoundsMetric, parse_total_hours

CASE = {"expected_keywords": ["Stripe", "panel"], "expected_hours_range": [50, 100]}
TEXT = "1. Pagos con Stripe — 14 h\n**Total estimado: 67 horas — USD 2.345**"


def test_parse_total_hours():
    assert parse_total_hours(TEXT) == 67
    assert parse_total_hours("**Total estimado: 1.250 horas**") == 1250
    assert parse_total_hours("sin total") is None


def test_content_recall_counts_keywords():
    result = ContentRecallMetric(threshold=0.6).evaluate(CASE, TEXT)
    assert result.score == 0.5 and not result.passed
    assert "panel" in result.details


def test_hours_bounds():
    assert HoursBoundsMetric().evaluate(CASE, TEXT).passed
    assert not HoursBoundsMetric().evaluate(CASE | {"expected_hours_range": [100, 200]}, TEXT).passed
    assert not HoursBoundsMetric().evaluate(CASE, "sin total").passed
