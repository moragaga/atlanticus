from __future__ import annotations

import pytest

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.errors import ToolConfigurationValidationError
from ada.contracts.tools.sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada.web.tools.configuration import ToolConfiguration, ToolRenderTopology
from ada.web.tools.configuration.web.models import (
    build_configuration_from_source_editor,
    source_editor_values_from_configuration,
)
from ada.web.tools.configuration.web.structure import (
    build_configuration_from_structure_editor,
    structure_editor_document_from_configuration,
)
from ada.web.tools.configuration.web.structure_ids import (
    STRUCTURE_BOTTOM_COMPONENT_ID,
    STRUCTURE_BOTTOM_COMPONENT_WRAPPER_ID,
)
from ada.web.tools.configuration.web.structure_presentation import (
    build_tool_structure_editor,
)


def _component(key: str) -> ToolComponent:
    return ToolComponent(
        key=key,
        display_name=key.replace('_', ' ').title(),
        subcomponents=(
            ToolSubcomponent(
                key=f'{key}_detail',
                display_name='Detalle',
            ),
        ),
    )


def _configuration(*, bottom_component_key: str | None = None) -> ToolConfiguration:
    key = 'process'
    return ToolConfiguration(
        tool_key=key,
        display_name='Proceso',
        kind=ToolConfigurationKind.PROCESS,
        source_consumption=ToolSourceConsumption(
            tool_key=key,
            source_keys=('pi',),
        ),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key=key,
            control_sources=(SourceControlPolicy('pi', 200, 300),),
        ),
        structure=ToolStructure(
            tool_key=key,
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.PLANT,
            center_component_key='center',
            components=(
                _component('left'),
                _component('center'),
                _component('detail'),
            ),
        ),
        render_topology=ToolRenderTopology(
            bottom_component_key=bottom_component_key,
        ),
    )


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


def test_render_topology_is_backward_compatible_when_bottom_is_absent() -> None:
    configuration = _configuration()

    document = configuration.to_document()

    assert 'render_topology' not in document
    assert ToolConfiguration.from_document(document).render_topology == ToolRenderTopology()


def test_process_bottom_component_round_trips_outside_tool_structure() -> None:
    configuration = _configuration(bottom_component_key='detail')

    document = configuration.to_document()
    restored = ToolConfiguration.from_document(document)

    assert document['render_topology'] == {'bottom_component_key': 'detail'}
    assert 'bottom_component_key' not in document['structure']
    assert restored.render_topology.bottom_component_key == 'detail'


def test_process_bottom_component_cannot_be_center() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='must differ from Process center component key',
    ):
        _configuration(bottom_component_key='center')


def test_process_bottom_component_must_reference_existing_component() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='must reference an existing component',
    ):
        _configuration(bottom_component_key='missing')


def test_integrated_operations_rejects_bottom_render_component() -> None:
    key = 'integrated'
    with pytest.raises(
        ToolConfigurationValidationError,
        match='only supported for Process',
    ):
        ToolConfiguration(
            tool_key=key,
            display_name='Integrado',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            source_consumption=ToolSourceConsumption(tool_key=key, source_keys=('pi',)),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key=key,
                control_sources=(SourceControlPolicy('pi', 200, 300),),
            ),
            structure=ToolStructure(
                tool_key=key,
                kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
                components=(
                    ToolComponent(
                        key='mine',
                        display_name='Mina',
                        scope=ToolScope.MINE,
                        subcomponents=(ToolSubcomponent(key='mine_detail', display_name='Mine'),),
                    ),
                    ToolComponent(
                        key='plant',
                        display_name='Planta',
                        scope=ToolScope.PLANT,
                        subcomponents=(ToolSubcomponent(key='plant_detail', display_name='Plant'),),
                    ),
                ),
            ),
            render_topology=ToolRenderTopology(bottom_component_key='plant'),
        )


def test_source_editor_preserves_render_topology_when_kind_is_unchanged() -> None:
    configuration = _configuration(bottom_component_key='detail')
    values = source_editor_values_from_configuration(configuration)

    rebuilt = build_configuration_from_source_editor(
        base_configuration=configuration,
        tool_key=None,
        values=values,
    )

    assert rebuilt.render_topology.bottom_component_key == 'detail'
    assert rebuilt.structure is configuration.structure


def test_structure_editor_document_preserves_render_topology_separately() -> None:
    configuration = _configuration(bottom_component_key='detail')

    editor_document = structure_editor_document_from_configuration(configuration)
    assert editor_document is not None

    assert editor_document['render_topology'] == {'bottom_component_key': 'detail'}
    rebuilt = build_configuration_from_structure_editor(
        base_configuration=configuration,
        structure_document=editor_document,
    )
    assert rebuilt.render_topology.bottom_component_key == 'detail'


def test_process_structure_editor_exposes_optional_bottom_selector() -> None:
    layout = build_tool_structure_editor(
        configuration_document=_configuration(bottom_component_key='detail').to_document()
    )

    selector = _find_by_id(layout, STRUCTURE_BOTTOM_COMPONENT_ID)
    wrapper = _find_by_id(layout, STRUCTURE_BOTTOM_COMPONENT_WRAPPER_ID)

    assert selector is not None
    assert selector.value == 'detail'
    assert selector.clearable is True
    assert selector.options == [
        {'label': 'Left', 'value': 'left'},
        {'label': 'Detail', 'value': 'detail'},
    ]
    assert wrapper is not None
    assert wrapper.hidden is False
