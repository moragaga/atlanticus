from __future__ import annotations

import json

from dash import html, page_container

from ada.configuration.tools import (
    ToolComponent,
    ToolConfigurationKind,
    ToolScope,
    ToolStructure,
    ToolSubcomponent,
)
from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.composition import AdaApplicationComposition
from ada.web.application.generic.layout import build_body_application_layout
from ada.web.application.generic.operational_render import build_operational_body
from ada.web.application.generic.runtime import create_application_runtime
from ada.web.component_store import ComponentStoreState, build_empty_component_stores
from ada.web.operational_render_binding import bind_operational_render
from atlanticus.web.services import ServiceRegistry


def _operational_binding():
    structure = ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='mine',
                display_name='Mina',
                scope=ToolScope.MINE,
                subcomponents=(ToolSubcomponent(key='mine_phase', display_name='Fase Mina'),),
            ),
            ToolComponent(
                key='plant',
                display_name='Planta',
                scope=ToolScope.PLANT,
                subcomponents=(ToolSubcomponent(key='plant_phase', display_name='Fase Planta'),),
            ),
        ),
    )
    return bind_operational_render(structure, build_empty_component_stores(structure))


def test_composition_factory_receives_complete_binding_in_structure_order() -> None:
    binding = _operational_binding()
    observed: list[tuple[tuple[str, str], ...]] = []

    def render_body(runtime_binding):
        component_state = tuple(
            (item.component.key, item.store.state.value) for item in runtime_binding.components
        )
        observed.append(component_state)
        return html.Div(
            [
                html.Section(
                    item.component.display_name,
                    id=f'ada-component-{item.component.key}',
                    **{'data-component-key': item.component.key},
                )
                for item in runtime_binding.components
            ],
            id='ada-operational-body',
        )

    composition = AdaApplicationComposition(
        modules=(),
        layout=build_body_application_layout,
        operational_body_factory=render_body,
    )
    definition = create_application_definition(
        composition=composition,
        operational_render_binding=binding,
    )

    application_layout = definition.layout(ServiceRegistry())
    main = application_layout.children
    body = main.children

    assert observed == [
        (
            ('mine', ComponentStoreState.EMPTY.value),
            ('plant', ComponentStoreState.EMPTY.value),
        )
    ]
    assert body.id == 'ada-operational-body'
    assert tuple(section.id for section in body.children) == (
        'ada-component-mine',
        'ada-component-plant',
    )


def test_binding_requires_explicit_application_body_factory() -> None:
    composition = AdaApplicationComposition(
        modules=(),
        layout=build_body_application_layout,
    )

    try:
        create_application_definition(
            composition=composition,
            operational_render_binding=_operational_binding(),
        )
    except ValueError as error:
        assert str(error) == 'Operational render binding requires an operational body factory'
    else:
        raise AssertionError('Expected missing operational body factory to fail')


def test_absent_binding_preserves_page_container() -> None:
    composition = AdaApplicationComposition(
        modules=(),
        layout=build_body_application_layout,
        operational_body_factory=lambda _binding: html.Div(id='unused-body'),
    )
    definition = create_application_definition(composition=composition)

    application_layout = definition.layout(ServiceRegistry())

    assert application_layout.children.children is page_container


def test_operational_body_factory_must_return_dash_component() -> None:
    binding = _operational_binding()

    try:
        build_operational_body(
            binding=binding,
            body_factory=lambda _binding: object(),
        )
    except TypeError as error:
        assert str(error) == 'Operational body factory must return a Dash Component'
    else:
        raise AssertionError('Expected invalid operational body factory result to fail')


def test_runtime_materializes_composition_owned_operational_body(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    binding = _operational_binding()

    def render_body(runtime_binding):
        return html.Div(
            [
                html.Div(item.component.display_name, id=f'runtime-{item.component.key}')
                for item in runtime_binding.components
            ],
            id='runtime-operational-body',
        )

    runtime = create_application_runtime(
        composition=AdaApplicationComposition(
            modules=(),
            layout=build_body_application_layout,
            operational_body_factory=render_body,
        ),
        operational_render_binding=binding,
    )
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert runtime.dash.server is runtime.server
    assert 'runtime-operational-body' in payload
    assert 'runtime-mine' in payload
    assert 'runtime-plant' in payload
