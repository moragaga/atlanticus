import pytest

from atlanticus.data_producers.pi import PiExecutionPlan, ResolvedPiTag
from atlanticus.integrations.pi.contracts import (
    PiExtractionMode,
    PiMaterialization,
    PiTagDefinition,
    PiValueKind,
)


def _definition(name: str, alias: str, mode: PiExtractionMode) -> PiTagDefinition:
    materializations = (
        (PiMaterialization.DAILY,)
        if mode is PiExtractionMode.RECORDED
        else (PiMaterialization.LATEST, PiMaterialization.DAILY)
    )
    return PiTagDefinition(
        tag_name=name,
        alias=alias,
        value_kind=PiValueKind.FLOAT,
        extraction_mode=mode,
        materializations=materializations,
    )


def test_execution_plan_indexes_resolved_tags_by_mode_and_real_pi_name() -> None:
    a = ResolvedPiTag(
        definition=_definition('TAG_A', 'a', PiExtractionMode.INTERPOLATED),
        web_id='WEB_A',
    )
    b = ResolvedPiTag(
        definition=_definition('TAG_B', 'b', PiExtractionMode.RECORDED),
        web_id='WEB_B',
    )
    plan = PiExecutionPlan(interpolated=(a,), recorded=(b,))

    assert plan.by_name == {
        (PiExtractionMode.INTERPOLATED, 'TAG_A'): a,
        (PiExtractionMode.RECORDED, 'TAG_B'): b,
    }
    assert a.alias == 'a'
    assert b.extraction_mode is PiExtractionMode.RECORDED


def test_execution_plan_preserves_identical_tags_in_different_modes() -> None:
    a = ResolvedPiTag(
        definition=_definition('TAG_A', 'same', PiExtractionMode.INTERPOLATED),
        web_id='WEB_A',
    )
    b = ResolvedPiTag(
        definition=_definition('TAG_A', 'same', PiExtractionMode.RECORDED),
        web_id='WEB_A',
    )

    plan = PiExecutionPlan(interpolated=(a,), recorded=(b,))

    assert plan.resolved == (a, b)
    assert plan.by_name == {
        (PiExtractionMode.INTERPOLATED, 'TAG_A'): a,
        (PiExtractionMode.RECORDED, 'TAG_A'): b,
    }


@pytest.mark.parametrize('mode', list(PiExtractionMode))
def test_execution_plan_rejects_duplicate_tags_within_mode(mode) -> None:
    a = ResolvedPiTag(
        definition=_definition('TAG_A', 'one', mode),
        web_id='WEB_A',
    )
    b = ResolvedPiTag(
        definition=_definition('tag_a', 'two', mode),
        web_id='WEB_A',
    )
    kwargs = {
        'interpolated': (a, b) if mode is PiExtractionMode.INTERPOLATED else (),
        'recorded': (a, b) if mode is PiExtractionMode.RECORDED else (),
    }

    with pytest.raises(ValueError, match='duplicate tag names'):
        PiExecutionPlan(**kwargs)
