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
    COMPONENT_ROW_TYPE,
    SUBCOMPONENT_ROW_TYPE,
)


def _configuration() -> dict[str, object]:
    return ToolConfiguration(
        tool_key='process',
        display_name='Proceso',
        kind=ToolConfigurationKind.PROCESS,
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
    ).to_document()


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


def test_structure_editor_has_dedicated_root_without_grid_component() -> None:
    layout = build_tool_structure_editor(configuration_document=_configuration())

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


def test_manual_structure_rows_use_pattern_matching_ids() -> None:
    document = _configuration()
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
    assert {'type': SUBCOMPONENT_ROW_TYPE, 'index': 0} in ids
