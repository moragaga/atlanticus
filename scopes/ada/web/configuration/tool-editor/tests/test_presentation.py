from dash.development.base_component import Component

from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.configuration.tools import ToolConfiguration, ToolConfigurationKind
from ada.web.configuration.tool_editor import build_tool_source_editor
from ada.web.configuration.tool_editor.ids import (
    ADDITIONAL_OBSERVATION_ID,
    CONFIGURATION_STORE_ID,
    DISPATCH_ENABLED_ID,
    PI_DEGRADING_ID,
    PI_PRE_DEGRADING_ID,
    ROOT_ID,
)


def _component_ids(component: Component) -> set[object]:
    resolved: set[object] = set()

    def visit(value: object) -> None:
        if isinstance(value, Component):
            component_id = getattr(value, 'id', None)
            if component_id is not None:
                resolved.add(component_id)
            children = getattr(value, 'children', None)
            if isinstance(children, (list, tuple)):
                for child in children:
                    visit(child)
            elif children is not None:
                visit(children)

    visit(component)
    return resolved


def _configuration() -> ToolConfiguration:
    return ToolConfiguration(
        tool_key='process',
        display_name='Process',
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
        ),
    )


def test_source_editor_exposes_required_source_controls() -> None:
    component = build_tool_source_editor()
    ids = _component_ids(component)

    assert ROOT_ID in ids
    assert CONFIGURATION_STORE_ID in ids
    assert PI_PRE_DEGRADING_ID in ids
    assert PI_DEGRADING_ID in ids
    assert DISPATCH_ENABLED_ID in ids
    assert ADDITIONAL_OBSERVATION_ID in ids


def test_source_editor_accepts_initial_tool_configuration_document() -> None:
    configuration = _configuration()

    component = build_tool_source_editor(configuration_document=configuration.to_document())

    configuration_store = next(
        child
        for child in component.children
        if getattr(child, 'id', None) == CONFIGURATION_STORE_ID
    )
    assert configuration_store.data == configuration.to_document()


def test_source_editor_does_not_embed_additional_source_catalog() -> None:
    component = build_tool_source_editor()
    rendered = str(component.to_plotly_json())

    assert 'blockgrade' not in rendered.casefold()
    assert 'geology' not in rendered.casefold()
