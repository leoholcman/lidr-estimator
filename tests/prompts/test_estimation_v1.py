"""Tests del template (no del modelo): corren en milisegundos, sin red."""

import pytest
from jinja2 import UndefinedError

from app.context.examples import ESTIMATION_EXAMPLES
from app.prompts import loader
from app.prompts.loader import render_estimation_prompt
from app.schemas import (
    DetailLevel,
    EstimationRequest,
    OutputFormat,
    ProjectType,
    ReferenceProject,
)

DESCRIPTION = "Una app para que los socios de un gimnasio reserven clases y paguen bonos."


def make_request(**overrides) -> EstimationRequest:
    data = {
        "description": DESCRIPTION,
        "project_type": ProjectType.MOBILE_APP,
        "detail_level": DetailLevel.MEDIUM,
        "output_format": OutputFormat.LINE_ITEMS,
    } | overrides
    return EstimationRequest(**data)


def test_user_prompt_wraps_description():
    _, user = render_estimation_prompt(make_request())
    assert f"<project_description>\n{DESCRIPTION}\n</project_description>" in user


def test_system_and_user_are_separate():
    system, user = render_estimation_prompt(make_request())
    assert DESCRIPTION not in system
    assert "Eres un estimador experto" not in user


@pytest.mark.parametrize(
    ("output_format", "expected"),
    [(OutputFormat.PHASES_TABLE, True), (OutputFormat.NARRATIVE, False)],
)
def test_phases_table_keyword_only_with_that_format(output_format, expected):
    system, _ = render_estimation_prompt(make_request(output_format=output_format))
    assert ("confidence_pct" in system) is expected
    assert ("phases_table" in system) is expected


@pytest.mark.parametrize(
    ("detail_level", "expected"),
    [(DetailLevel.DETAILED, True), (DetailLevel.SUMMARY, False)],
)
def test_assumptions_per_phase_only_when_detailed(detail_level, expected):
    system, _ = render_estimation_prompt(make_request(detail_level=detail_level))
    assert ("asunciones por fase" in system) is expected


def test_examples_are_included():
    system, _ = render_estimation_prompt(make_request())
    for example in ESTIMATION_EXAMPLES:
        assert example["meeting_summary"] in system
    assert system.count("<ejemplo numero=") == len(ESTIMATION_EXAMPLES)


def test_reference_projects_rendered_only_when_present():
    _, without = render_estimation_prompt(make_request())
    assert "<proyectos_similares>" not in without

    refs = [ReferenceProject(name="Gym Lite", summary="Reservas de clases", actual_hours=120)]
    _, with_refs = render_estimation_prompt(make_request(reference_projects=refs))
    assert "Gym Lite (120 h reales)" in with_refs


def test_v2_differs_from_v1():
    v1, _ = render_estimation_prompt(make_request(), "v1")
    v2, _ = render_estimation_prompt(make_request(), "v2")
    assert v1 != v2
    assert "25%" in v2


def test_unknown_version_raises():
    with pytest.raises(ValueError):
        render_estimation_prompt(make_request(), "v99")


def test_strict_undefined_fails_on_missing_variable():
    with pytest.raises(UndefinedError):
        loader._env.from_string("{{ no_existe }}").render()
