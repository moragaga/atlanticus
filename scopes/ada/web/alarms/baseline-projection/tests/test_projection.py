import pytest

from ada.configuration.tools import (
    ProcessLayoutRole,
    ToolComponent,
    ToolConfigurationKind,
    ToolScope,
    ToolStructure,
    ToolSubcomponent,
)
from ada.web.alarms.baseline_projection import (
    AlarmBaselineAnchorKind,
    AlarmBaselineProjectionError,
    project_alarm_baseline,
)


def _subcomponent(
    key: str,
    *,
    linked_component_keys: tuple[str, ...] = (),
) -> ToolSubcomponent:
    return ToolSubcomponent(
        key=key,
        display_name=key.replace('_', ' ').title(),
        linked_component_keys=linked_component_keys,
    )


def _process_structure(*, center_subcomponents: tuple[ToolSubcomponent, ...]) -> ToolStructure:
    return ToolStructure(
        tool_key='mina_process',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.MINE,
        components=(
            ToolComponent(
                key='left_context',
                display_name='Left Context',
                layout_role=ProcessLayoutRole.LEFT,
            ),
            ToolComponent(
                key='mina',
                display_name='Mina',
                layout_role=ProcessLayoutRole.CENTER,
                subcomponents=center_subcomponents,
            ),
            ToolComponent(
                key='right_context',
                display_name='Right Context',
                layout_role=ProcessLayoutRole.RIGHT,
            ),
        ),
    )


def _integrated_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='carguio',
                display_name='Carguío',
                scope=ToolScope.MINE,
                subcomponents=(
                    _subcomponent(
                        'gestion_carguio_turno',
                        linked_component_keys=('transporte',),
                    ),
                ),
            ),
            ToolComponent(
                key='transporte',
                display_name='Transporte',
                scope=ToolScope.MINE,
                subcomponents=(_subcomponent('transporte_global'),),
            ),
            ToolComponent(
                key='molienda',
                display_name='Molienda',
                scope=ToolScope.PLANT,
                subcomponents=(_subcomponent('molienda'),),
            ),
        ),
    )


def test_process_projects_exactly_one_center_anchor() -> None:
    projection = project_alarm_baseline(
        _process_structure(center_subcomponents=(_subcomponent('principal'),))
    )

    assert projection.tool_key == 'mina_process'
    assert projection.kind is ToolConfigurationKind.PROCESS
    assert len(projection.points) == 1
    point = projection.points[0]
    assert point.anchor_kind is AlarmBaselineAnchorKind.LAYOUT_ROLE
    assert point.anchor_key == 'center'
    assert point.component_key == 'mina'
    assert point.display_name == 'Mina'
    assert point.scope is ToolScope.MINE


def test_process_multiple_center_subcomponents_still_project_one_point() -> None:
    projection = project_alarm_baseline(
        _process_structure(
            center_subcomponents=(
                _subcomponent('carguio'),
                _subcomponent('transporte'),
                _subcomponent('chancado'),
            )
        )
    )

    assert projection.component_keys == ('mina',)
    assert len(projection.points) == 1


def test_process_optional_non_center_regions_do_not_create_baseline_points() -> None:
    projection = project_alarm_baseline(
        _process_structure(center_subcomponents=(_subcomponent('principal'),))
    )

    assert 'left_context' not in projection.component_keys
    assert 'right_context' not in projection.component_keys


def test_process_single_full_size_subcomponent_still_uses_center_anchor() -> None:
    structure = ToolStructure(
        tool_key='flotacion',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        components=(
            ToolComponent(
                key='flotacion',
                display_name='Flotación',
                layout_role=ProcessLayoutRole.CENTER,
                subcomponents=(_subcomponent('flotacion'),),
            ),
        ),
    )

    projection = project_alarm_baseline(structure)

    assert projection.points[0].anchor_key == 'center'
    assert projection.points[0].component_key == 'flotacion'
    assert projection.points[0].scope is ToolScope.PLANT


def test_integrated_operations_projects_one_point_per_component_in_declared_order() -> None:
    projection = project_alarm_baseline(_integrated_structure())

    assert projection.kind is ToolConfigurationKind.INTEGRATED_OPERATIONS
    assert projection.component_keys == ('carguio', 'transporte', 'molienda')
    assert tuple(point.anchor_key for point in projection.points) == projection.component_keys
    assert all(
        point.anchor_kind is AlarmBaselineAnchorKind.COMPONENT for point in projection.points
    )


def test_integrated_operations_preserves_component_scopes() -> None:
    projection = project_alarm_baseline(_integrated_structure())

    assert tuple(point.scope for point in projection.points) == (
        ToolScope.MINE,
        ToolScope.MINE,
        ToolScope.PLANT,
    )


def test_integrated_operations_accepts_single_component_without_fixed_count() -> None:
    structure = ToolStructure(
        tool_key='small_integrated',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='process_a',
                display_name='Process A',
                scope=ToolScope.MINE,
                subcomponents=(_subcomponent('detail'),),
            ),
        ),
    )

    projection = project_alarm_baseline(structure)

    assert projection.component_keys == ('process_a',)


def test_shared_subcomponent_relationship_does_not_duplicate_baseline_points() -> None:
    projection = project_alarm_baseline(_integrated_structure())

    assert projection.component_keys == ('carguio', 'transporte', 'molienda')
    assert len(projection.points) == 3


def test_projection_serializes_as_ui_neutral_document() -> None:
    document = project_alarm_baseline(_integrated_structure()).to_document()

    assert document == {
        'tool_key': 'integrated_operations',
        'kind': 'integrated_operations',
        'points': [
            {
                'anchor_kind': 'component',
                'anchor_key': 'carguio',
                'component_key': 'carguio',
                'display_name': 'Carguío',
                'scope': 'mine',
            },
            {
                'anchor_kind': 'component',
                'anchor_key': 'transporte',
                'component_key': 'transporte',
                'display_name': 'Transporte',
                'scope': 'mine',
            },
            {
                'anchor_kind': 'component',
                'anchor_key': 'molienda',
                'component_key': 'molienda',
                'display_name': 'Molienda',
                'scope': 'plant',
            },
        ],
    }


def test_process_document_keeps_center_anchor_and_real_component_identity() -> None:
    document = project_alarm_baseline(
        _process_structure(center_subcomponents=(_subcomponent('principal'),))
    ).to_document()

    assert document['points'] == [
        {
            'anchor_kind': 'layout_role',
            'anchor_key': 'center',
            'component_key': 'mina',
            'display_name': 'Mina',
            'scope': 'mine',
        }
    ]


def test_projection_requires_tool_structure() -> None:
    with pytest.raises(TypeError, match='Tool Structure is required'):
        project_alarm_baseline(object())


def test_projection_model_rejects_empty_points() -> None:
    from ada.web.alarms.baseline_projection import AlarmBaselineProjection

    with pytest.raises(AlarmBaselineProjectionError, match='requires points'):
        AlarmBaselineProjection(
            tool_key='tool',
            kind=ToolConfigurationKind.PROCESS,
            points=(),
        )
