from __future__ import annotations

from datetime import UTC, datetime
from dash import Output
from dash.development.base_component import Component

from ada.web.kpis.configuration import (
    KpiConfiguration,
    KpiConfigurationBinding,
    KpiDestination,
    KpiDestinationCatalog,
    KpiDestinationCatalogSnapshot,
)
from ada.web.kpis.configuration.web import (
    KpiConfigurationEditorContext,
    build_kpi_configuration_editor_surface,
    register_kpi_configuration_editor_callbacks,
    creation_state,
    save_binding,
)
from ada.web.kpis.configuration.web.ids import ADD_BUTTON_ID, EDITOR_HOURS_ID
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


class Destinations:
    def __init__(self, with_component: bool = True) -> None:
        items = [
            KpiDestination(key='global_indicators', display_name='Global Indicators'),
            KpiDestination(key='time_status', display_name='Time Status'),
        ]
        if with_component:
            items.append(KpiDestination(key='plant', display_name='Planta'))
        self.snapshot = KpiDestinationCatalogSnapshot(
            projection_target=ProjectionTarget(
                source_key=SourceKey('ada-tool-configuration'),
                source_release=SourceReleaseRef(
                    release_id=SourceReleaseId('tools-r1'),
                    published_at_utc=datetime(2026, 9, 16, tzinfo=UTC),
                ),
            ),
            catalog=KpiDestinationCatalog(destinations=tuple(items)),
        )

    def load(self):
        return self.snapshot


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


class _CallbackRecorder:
    def __init__(self) -> None:
        self.callbacks: list[tuple[tuple[object, ...], dict[str, object], object]] = []

    def callback(self, *dependencies: object, **options: object):
        def register(function):
            self.callbacks.append((dependencies, options, function))
            return function

        return register

    def function_for_output(self, component_id: object, component_property: str):
        matches = [
            function
            for dependencies, _options, function in self.callbacks
            if any(
                isinstance(dependency, Output)
                and dependency.component_id == component_id
                and dependency.component_property == component_property
                for dependency in dependencies
            )
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"Expected one callback for {component_id!r}.{component_property}, found {len(matches)}"
            )
        return matches[0]


def test_series_hours_callback_controls_hours_visibility() -> None:
    context = KpiConfigurationEditorContext(destinations=Destinations())
    recorder = _CallbackRecorder()
    register_kpi_configuration_editor_callbacks(recorder, context)
    toggle = recorder.function_for_output(EDITOR_HOURS_ID, 'disabled')

    assert toggle([]) == (True, True)
    assert toggle(['enabled']) == (False, False)

def test_creation_requires_a_real_tool_component() -> None:
    assert creation_state(None)[0] is False
    assert creation_state(Destinations(with_component=False).load().catalog)[0] is False
    assert creation_state(Destinations(with_component=True).load().catalog) == (True, None)


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


def test_second_create_preserves_first_binding() -> None:
    first = save_binding(
        KpiConfiguration(),
        {'mode': 'create'},
        kpi_key='availability',
        latest_enabled=True,
        series_enabled=False,
        series_hours=None,
        destination_keys=('plant',),
        creation_allowed=True,
    )
    second = save_binding(
        first,
        {'mode': 'create'},
        kpi_key='throughput',
        latest_enabled=True,
        series_enabled=True,
        series_hours=12,
        destination_keys=('plant',),
        creation_allowed=True,
    )

    assert tuple(item.kpi_key for item in second.bindings) == (
        'availability',
        'throughput',
    )


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
