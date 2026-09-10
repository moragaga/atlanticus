from __future__ import annotations

from types import SimpleNamespace

from dash import Dash
from dash.development.base_component import Component

from ada.web.kpis.configuration import (
    KpiConfiguration,
    KpiConfigurationBinding,
    KpiDestination,
    KpiDestinationCatalog,
)
from ada.web.kpis.configuration.web import (
    KpiConfigurationEditorContext,
    build_kpi_configuration_editor_surface,
    create_kpi_configuration_editor_module,
    creation_state,
    save_binding,
)
from ada.web.kpis.configuration.web.ids import ADD_BUTTON_ID


class Destinations:
    def __init__(self, with_component: bool = True) -> None:
        items = [
            KpiDestination(key='global_indicators', display_name='Global Indicators'),
            KpiDestination(key='time_status', display_name='Time Status'),
        ]
        if with_component:
            items.append(KpiDestination(key='plant', display_name='Planta'))
        self.catalog = KpiDestinationCatalog(
            tool_projection_revision='tools-r1',
            destinations=tuple(items),
        )

    def load(self):
        return self.catalog


def _walk(component: object) -> list[Component]:
    found: list[Component] = []
    if isinstance(component, Component):
        found.append(component)
        children = getattr(component, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                found.extend(_walk(child))
        elif children is not None:
            found.extend(_walk(children))
    return found


def test_creation_requires_a_real_tool_component() -> None:
    assert creation_state(None)[0] is False
    assert creation_state(Destinations(with_component=False).load())[0] is False
    assert creation_state(Destinations(with_component=True).load()) == (True, None)


def test_editor_surface_disables_creation_without_component() -> None:
    context = KpiConfigurationEditorContext(
        destinations=Destinations(with_component=False),
    )
    layout = build_kpi_configuration_editor_surface(context)
    add = next(
        node
        for node in _walk(layout)
        if getattr(node, 'id', None) == ADD_BUTTON_ID
    )
    assert add.disabled is True


def test_editor_module_registers_callbacks() -> None:
    context = KpiConfigurationEditorContext(destinations=Destinations())
    module = create_kpi_configuration_editor_module(context)
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = build_kpi_configuration_editor_surface(context)

    assert module.register_callbacks is not None
    module.register_callbacks(app, SimpleNamespace())

    assert len(app.callback_map) >= 5


def test_save_binding_supports_create_and_edit() -> None:
    created = save_binding(
        KpiConfiguration(),
        {'mode': 'create'},
        kpi_key='availability',
        latest_enabled=True,
        series_enabled=True,
        series_hours=12,
        destination_keys=('plant',),
        creation_allowed=True,
    )
    assert created.binding('availability') == KpiConfigurationBinding(
        kpi_key='availability',
        destination_keys=('plant',),
        latest_enabled=True,
        series_enabled=True,
        series_hours=12,
    )

    edited = save_binding(
        created,
        {'mode': 'edit', 'key': 'availability'},
        kpi_key='availability',
        latest_enabled=False,
        series_enabled=True,
        series_hours=6,
        destination_keys=('plant',),
        creation_allowed=True,
    )
    binding = edited.binding('availability')
    assert binding is not None
    assert binding.latest_enabled is False
    assert binding.series_hours == 6
