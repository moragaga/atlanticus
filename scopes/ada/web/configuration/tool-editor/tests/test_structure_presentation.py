from pathlib import Path

from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.configuration.tools import ToolConfiguration, ToolConfigurationKind
from ada.web.configuration.tool_editor import (
    STRUCTURE_ROOT_ID,
    TOOL_CONFIGURATION_EDITOR_ROOT_ID,
    build_tool_configuration_editor,
    build_tool_structure_editor,
)
from ada.web.configuration.tool_editor.structure_ids import (
    COMPONENT_ADD_SUBCOMPONENT_TYPE,
    COMPONENT_ROW_TYPE,
    COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
    SUBCOMPONENT_LINKED_TYPE,
    SUBCOMPONENT_ROW_TYPE,
)


def _configuration(
    kind: ToolConfigurationKind = ToolConfigurationKind.PROCESS,
) -> ToolConfiguration:
    return ToolConfiguration(
        tool_key='process',
        display_name='Proceso',
        kind=kind,
        source_consumption=ToolSourceConsumption(
            tool_key='process',
            source_keys=('pi',),
        ),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key='process',
            control_sources=(
                SourceControlPolicy(
                    source_key='pi',
                    pre_degrading_after_seconds=200,
                    degrading_after_seconds=300,
                ),
            ),
            additional_observation_source_keys=(),
        ),
        structure=None,
    )


def _ids(component) -> list[object]:
    resolved: list[object] = []
    component_id = getattr(component, 'id', None)
    if component_id is not None:
        resolved.append(component_id)
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, 'children') or hasattr(child, 'id'):
                resolved.extend(_ids(child))
    elif hasattr(children, 'children') or hasattr(children, 'id'):
        resolved.extend(_ids(children))
    return resolved


def _find_by_id(component, component_id):
    if getattr(component, 'id', None) == component_id:
        return component
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, 'children') or hasattr(child, 'id'):
                found = _find_by_id(child, component_id)
                if found is not None:
                    return found
    elif hasattr(children, 'children') or hasattr(children, 'id'):
        return _find_by_id(children, component_id)
    return None


def test_structure_editor_has_dedicated_root_without_grid_component() -> None:
    layout = build_tool_structure_editor(
        configuration_document=_configuration().to_document()
    )

    assert layout.id == STRUCTURE_ROOT_ID
    source = (
        Path(__file__).parents[1]
        / 'src'
        / 'ada'
        / 'web'
        / 'configuration'
        / 'tool_editor'
        / 'structure_presentation.py'
    ).read_text(encoding='utf-8')
    assert 'dash_table' not in source
    assert 'DataTable' not in source


def test_complete_editor_composes_sources_and_structure() -> None:
    layout = build_tool_configuration_editor()

    assert layout.id == TOOL_CONFIGURATION_EDITOR_ROOT_ID
    assert len(layout.children) == 2
    assert 'atlanticus-bootstrap' in layout.className


def test_subcomponents_are_nested_under_their_owner_component() -> None:
    document = _configuration().to_document()
    document['structure'] = {
        'tool_key': 'process',
        'kind': 'process',
        'operational_scope': 'plant',
        'components': [
            {
                'key': 'crusher',
                'display_name': 'Chancado',
                'scope': None,
                'layout_role': 'center',
                'subcomponents': [
                    {
                        'key': 'primary',
                        'display_name': 'Primario',
                        'linked_component_keys': [],
                    }
                ],
            }
        ],
    }

    layout = build_tool_structure_editor(configuration_document=document)
    ids = _ids(layout)

    assert {'type': COMPONENT_ROW_TYPE, 'index': 0} in ids
    assert {
        'type': COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
        'owner_index': 0,
    } in ids
    assert {
        'type': COMPONENT_ADD_SUBCOMPONENT_TYPE,
        'owner_index': 0,
    } in ids
    assert {
        'type': SUBCOMPONENT_ROW_TYPE,
        'index': 0,
        'owner_index': 0,
    } in ids


def test_integrated_operations_link_selector_excludes_owner_and_other_scope() -> None:
    document = _configuration(
        ToolConfigurationKind.INTEGRATED_OPERATIONS
    ).to_document()
    document['structure'] = {
        'tool_key': 'process',
        'kind': 'integrated_operations',
        'operational_scope': None,
        'components': [
            {
                'key': 'mine',
                'display_name': 'Mina',
                'scope': 'mine',
                'layout_role': None,
                'subcomponents': [
                    {
                        'key': 'extraction',
                        'display_name': 'Extracción',
                        'linked_component_keys': ['dispatch'],
                    }
                ],
            },
            {
                'key': 'dispatch',
                'display_name': 'Despacho',
                'scope': 'mine',
                'layout_role': None,
                'subcomponents': [
                    {
                        'key': 'fleet',
                        'display_name': 'Flota',
                        'linked_component_keys': [],
                    }
                ],
            },
            {
                'key': 'plant',
                'display_name': 'Planta',
                'scope': 'plant',
                'layout_role': None,
                'subcomponents': [
                    {
                        'key': 'crusher',
                        'display_name': 'Chancado',
                        'linked_component_keys': [],
                    }
                ],
            },
        ],
    }

    layout = build_tool_structure_editor(configuration_document=document)
    linked_id = {
        'type': SUBCOMPONENT_LINKED_TYPE,
        'index': 0,
        'owner_index': 0,
    }
    linked = _find_by_id(layout, linked_id)

    assert linked is not None
    assert linked.value == ['dispatch']
    assert linked.options == [
        {'label': 'Despacho', 'value': 'dispatch'}
    ]
