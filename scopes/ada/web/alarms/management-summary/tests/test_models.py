import pytest

from ada.web.alarms.management_summary import (
    AlarmManagementSummaryArea,
    AlarmManagementSummaryDefinitionError,
    AlarmManagementSummarySegmentState,
    AlarmManagementSummaryState,
    AlarmManagementSummaryTone,
)


def _segment(
    area: AlarmManagementSummaryArea,
    *,
    group: str = 'G3',
    percentage: float = 60,
    tone: AlarmManagementSummaryTone = AlarmManagementSummaryTone.NEUTRAL,
) -> AlarmManagementSummarySegmentState:
    return AlarmManagementSummarySegmentState(
        area=area,
        group=group,
        management_percentage=percentage,
        tone=tone,
    )


def test_summary_supports_mine_and_plant_without_tool_manifest() -> None:
    state = AlarmManagementSummaryState(
        segments=(
            _segment(AlarmManagementSummaryArea.MINE),
            _segment(AlarmManagementSummaryArea.PLANT, group='G1', percentage=45),
        )
    )

    assert tuple(segment.area for segment in state.segments) == (
        AlarmManagementSummaryArea.MINE,
        AlarmManagementSummaryArea.PLANT,
    )


def test_summary_allows_one_area_for_tool_filtered_composition() -> None:
    state = AlarmManagementSummaryState.from_iterable((_segment(AlarmManagementSummaryArea.MINE),))

    assert len(state.segments) == 1
    assert state.segments[0].area is AlarmManagementSummaryArea.MINE


def test_summary_rejects_duplicate_areas() -> None:
    with pytest.raises(AlarmManagementSummaryDefinitionError, match='duplicate areas'):
        AlarmManagementSummaryState(
            segments=(
                _segment(AlarmManagementSummaryArea.MINE),
                _segment(AlarmManagementSummaryArea.MINE, group='G4'),
            )
        )


def test_segment_normalizes_group_and_validates_percentage() -> None:
    segment = _segment(
        AlarmManagementSummaryArea.PLANT,
        group='  G2  ',
        percentage=72.5,
        tone=AlarmManagementSummaryTone.ATTENTION,
    )

    assert segment.group == 'G2'
    assert segment.management_percentage == 72.5
    assert segment.tone is AlarmManagementSummaryTone.ATTENTION

    with pytest.raises(AlarmManagementSummaryDefinitionError, match='between 0 and 100'):
        _segment(AlarmManagementSummaryArea.PLANT, percentage=101)
