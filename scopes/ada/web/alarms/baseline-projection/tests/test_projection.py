import pytest

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import (
    ToolComponent,
    ToolStructure,
    ToolSubcomponent,
)
from ada.web.alarms.baseline_projection import (
    AlarmBaselineAnchorKind,
    AlarmBaselineProjectionError,
    project_alarm_baseline,
)


def _subcomponent(key: str) -> ToolSubcomponent:
    return ToolSubcomponent(
        key=key,
        display_name=key.replace('_', ' ').title(),
    )


def _process_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='process_tool',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        center_component_key='center',
        components=(
            ToolComponent(
                key='left',
                display_name='Left',
                subcomponents=(_subcomponent('left_detail'),),
            ),
            ToolComponent(
                key='center',
                display_name='Center',
                subcomponents=(_subcomponent('center_detail'),),
            ),
            ToolComponent(
                key='right',
                display_name='Right',
                scope=ToolScope.MINE,
                subcomponents=(_subcomponent('right_detail'),),
            ),
            ToolComponent(
                key='detail',
                display_name='Detail',
                subcomponents=(_subcomponent('detail_view'),),
            ),
        ),
    )


def _integrated_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='mine',
                display_name='Mina',
                scope=ToolScope.MINE,
                subcomponents=(_subcomponent('mine_detail'),),
            ),
            ToolComponent(
                key='plant',
                display_name='Planta',
                scope=ToolScope.PLANT,
                subcomponents=(_subcomponent('plant_detail'),),
            ),
        ),
    )


def test_process_projects_all_components_to_main_in_declared_order_without_bottom() -> None:
    projection = project_alarm_baseline(_process_structure())

    assert projection.tool_key == 'process_tool'
    assert projection.kind is ToolConfigurationKind.PROCESS
    assert projection.main_component_keys == ('left', 'center', 'right', 'detail')
    assert projection.bottom_point is None
    assert all(
        point.anchor_kind is AlarmBaselineAnchorKind.COMPONENT
        for point in projection.main_points
    )


def test_process_projects_optional_bottom_separately_from_main_order() -> None:
    projection = project_alarm_baseline(
        _process_structure(),
        bottom_component_key='detail',
    )

    assert projection.main_component_keys == ('left', 'center', 'right')
    assert projection.bottom_component_key == 'detail'
    assert projection.bottom_point is not None
    assert projection.bottom_point.component_key == 'detail'


def test_process_resolves_inherited_and_explicit_component_scopes() -> None:
    projection = project_alarm_baseline(
        _process_structure(),
        bottom_component_key='detail',
    )

    assert tuple(point.scope for point in projection.main_points) == (
        ToolScope.PLANT,
        ToolScope.PLANT,
        ToolScope.MINE,
    )
    assert projection.bottom_point is not None
    assert projection.bottom_point.scope is ToolScope.PLANT


def test_process_subcomponents_do_not_create_baseline_points() -> None:
    projection = project_alarm_baseline(_process_structure())

    assert projection.component_keys == ('left', 'center', 'right', 'detail')
    assert 'center_detail' not in projection.component_keys


def test_process_bottom_cannot_be_center_component() -> None:
    with pytest.raises(
        AlarmBaselineProjectionError,
        match='must differ from Process center component',
    ):
        project_alarm_baseline(
            _process_structure(),
            bottom_component_key='center',
        )


def test_process_bottom_must_reference_component() -> None:
    with pytest.raises(
        AlarmBaselineProjectionError,
        match='must reference a Tool component',
    ):
        project_alarm_baseline(
            _process_structure(),
            bottom_component_key='missing',
        )


def test_integrated_operations_preserves_declared_order_and_scopes() -> None:
    projection = project_alarm_baseline(_integrated_structure())

    assert projection.kind is ToolConfigurationKind.INTEGRATED_OPERATIONS
    assert projection.main_component_keys == ('mine', 'plant')
    assert projection.bottom_point is None
    assert tuple(point.scope for point in projection.main_points) == (
        ToolScope.MINE,
        ToolScope.PLANT,
    )


def test_integrated_operations_rejects_bottom() -> None:
    with pytest.raises(
        AlarmBaselineProjectionError,
        match='only supported for Process',
    ):
        project_alarm_baseline(
            _integrated_structure(),
            bottom_component_key='plant',
        )


def test_projection_serializes_static_regions_without_runtime_alarm_state() -> None:
    document = project_alarm_baseline(
        _process_structure(),
        bottom_component_key='detail',
    ).to_document()

    assert document['tool_key'] == 'process_tool'
    assert document['kind'] == 'process'
    assert [point['component_key'] for point in document['main_points']] == [
        'left',
        'center',
        'right',
    ]
    assert document['bottom_point']['component_key'] == 'detail'
    assert 'alarms' not in document
    assert 'routes' not in document
    assert 'preview' not in document


def test_projection_requires_tool_structure() -> None:
    with pytest.raises(TypeError, match='Tool Structure is required'):
        project_alarm_baseline(object())
