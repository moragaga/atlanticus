from ada.configuration.tools import ToolConfiguration, ToolConfigurationKind
from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.web.configuration.tool_editor import build_tool_structure_editor
from ada.web.configuration.tool_editor.structure_ids import (
    COMPONENT_ADD_SUBCOMPONENT_TYPE,
    COMPONENT_KEY_TYPE,
    COMPONENT_ROW_TYPE,
    COMPONENT_SUMMARY_NAME_TYPE,
    COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
    SUBCOMPONENT_KEY_TYPE,
    SUBCOMPONENT_LINKED_TYPE,
    SUBCOMPONENT_ROW_TYPE,
)


def _configuration() -> dict[str, object]:
    configuration = ToolConfiguration(
        tool_key='integrated_operations',
        display_name='Operaciones Integradas',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        source_consumption=ToolSourceConsumption(
            tool_key='integrated_operations',
            source_keys=('pi',),
        ),
        source_operational_participation=(
            ToolSourceOperationalParticipation(
                tool_key='integrated_operations',
                control_sources=(
                    SourceControlPolicy('pi', 200, 300),
                ),
            )
        ),
    )
    document = configuration.to_document()
    document['structure'] = {
        'tool_key': 'integrated_operations',
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
    return document


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


def test_subcomponents_are_nested_under_owner_component() -> None:
    layout = build_tool_structure_editor(
        configuration_document=_configuration()
    )
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


def test_shared_visibility_excludes_owner_and_incompatible_scope() -> None:
    layout = build_tool_structure_editor(
        configuration_document=_configuration()
    )
    linked = _find_by_id(
        layout,
        {
            'type': SUBCOMPONENT_LINKED_TYPE,
            'index': 0,
            'owner_index': 0,
        },
    )

    assert linked is not None
    assert linked.value == ['dispatch']
    assert linked.options == [
        {'label': 'Despacho', 'value': 'dispatch'}
    ]
def test_structure_uses_compact_summary_and_internal_keys() -> None:
    layout = build_tool_structure_editor(
        configuration_document=_configuration()
    )
    ids = _ids(layout)

    assert {'type': COMPONENT_KEY_TYPE, 'index': 0} in ids
    assert {
        'type': COMPONENT_SUMMARY_NAME_TYPE,
        'index': 0,
    } in ids
    assert {
        'type': SUBCOMPONENT_KEY_TYPE,
        'index': 0,
        'owner_index': 0,
    } in ids

    rendered = str(layout.to_plotly_json())
    assert 'Identificador' not in rendered
    assert 'Posición' not in rendered
    assert 'Eliminar subcomponente' in rendered

def test_structure_inputs_do_not_depend_on_bootstrap_form_control() -> None:
    rendered = str(
        build_tool_structure_editor(configuration_document=_configuration()).to_plotly_json()
    )

    assert 'form-control' not in rendered
