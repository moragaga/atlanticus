from dash.development.base_component import Component

from ada.web.configuration.tool_editor import (
    BRANDING_ID,
    COVERAGE_ID,
    DISPATCH_DEGRADATION_ID,
    DISPATCH_ENABLED_ID,
    DISPATCH_PREVENTIVE_ID,
    DISPLAY_NAME_ID,
    KIND_ID,
    PI_DEGRADATION_ID,
    PI_PREVENTIVE_ID,
    build_tool_source_editor,
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


def test_tool_editor_exposes_general_and_independent_source_state_controls() -> None:
    component = build_tool_source_editor()
    ids = _component_ids(component)

    assert DISPLAY_NAME_ID in ids
    assert KIND_ID in ids
    assert COVERAGE_ID in ids
    assert BRANDING_ID in ids
    assert PI_PREVENTIVE_ID in ids
    assert PI_DEGRADATION_ID in ids
    assert DISPATCH_PREVENTIVE_ID in ids
    assert DISPATCH_DEGRADATION_ID in ids
    assert DISPATCH_ENABLED_ID in ids


def test_tool_editor_does_not_expose_legacy_source_configuration() -> None:
    rendered = str(build_tool_source_editor().to_plotly_json()).casefold()

    assert 'pre-degrading' not in rendered
    assert 'observaciones adicionales' not in rendered
    assert 'additional observation' not in rendered
    assert 'source_key_adicional' not in rendered
    assert 'comparte el umbral preventivo' not in rendered

def test_tool_source_inputs_do_not_depend_on_bootstrap_form_control() -> None:
    rendered = str(build_tool_source_editor().to_plotly_json())

    assert 'form-control' not in rendered
