# Integra el collector con Atlanticus Web: registra servicios, arranca el poller sólo con tráfico
# real de aplicación y conecta el cache de proceso con los stores de navegador.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dash import Input, Output, State, dcc
from dash.development.base_component import Component
from flask import request

from ada.web.kpis.collector.presentation import (
    KpiCollectorPresentationSettings,
    KpiCollectorPresentationSource,
    component_kpi_store_id,
    project_component_store_data,
    resolve_kpi_collector_browser_update,
)
from ada.web.kpis.collector.runtime import (
    AdaKpiCollectorPollingRuntime,
    KpiCollectorPollingSettings,
)
from ada.web.tools.structure import ToolStructure
from atlanticus.web.modules import CallbackRegistrar, WebModule
from atlanticus.web.services import ServiceRegistry

if TYPE_CHECKING:
    from dash import Dash
    from flask import Flask

ADA_KPI_COLLECTOR_SERVICE_KEY = 'ada.kpi.collector'
ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY = 'ada.kpi.collector.runtime'
_START_EXCLUDED_PATH_PREFIXES = ('/health/', '/assets/', '/.auth/')

LayoutFactory = Callable[..., object]


@dataclass(frozen=True, slots=True)
class AdaKpiCollectorWebIntegration:
    module: WebModule
    collector: KpiCollectorPresentationSource
    presentation_settings: KpiCollectorPresentationSettings

    def wrap_layout(self, layout: LayoutFactory) -> LayoutFactory:
        if not callable(layout):
            raise TypeError('layout must be callable')

        def wrapped_layout(*args: object, **kwargs: object) -> Component:
            resolved = layout(*args, **kwargs)
            if not isinstance(resolved, Component):
                raise TypeError('KPI collector integration requires a Dash Component layout')
            _append_runtime_components(
                resolved,
                _build_runtime_components(
                    collector=self.collector,
                    settings=self.presentation_settings,
                ),
            )
            return resolved

        return wrapped_layout


def create_ada_kpi_collector_module(
    collector: object,
    *,
    polling_settings: KpiCollectorPollingSettings | None = None,
) -> WebModule:
    polling_runtime = AdaKpiCollectorPollingRuntime(
        collector,
        settings=polling_settings,
    )
    return _create_module(
        collector=collector,
        polling_runtime=polling_runtime,
        register_callbacks=None,
    )


def create_ada_kpi_collector_web_integration(
    collector: KpiCollectorPresentationSource,
    *,
    polling_settings: KpiCollectorPollingSettings | None = None,
    presentation_settings: KpiCollectorPresentationSettings | None = None,
) -> AdaKpiCollectorWebIntegration:
    if not isinstance(collector.structure, ToolStructure):
        raise TypeError('collector structure must be ToolStructure')
    resolved_presentation_settings = presentation_settings or KpiCollectorPresentationSettings()
    if not isinstance(resolved_presentation_settings, KpiCollectorPresentationSettings):
        raise TypeError('presentation_settings must be KpiCollectorPresentationSettings')
    polling_runtime = AdaKpiCollectorPollingRuntime(
        collector,
        settings=polling_settings,
    )
    register_callbacks = _create_callback_registrar(
        structure=collector.structure,
        settings=resolved_presentation_settings,
    )
    return AdaKpiCollectorWebIntegration(
        module=_create_module(
            collector=collector,
            polling_runtime=polling_runtime,
            register_callbacks=register_callbacks,
        ),
        collector=collector,
        presentation_settings=resolved_presentation_settings,
    )


def _create_module(
    *,
    collector: object,
    polling_runtime: AdaKpiCollectorPollingRuntime,
    register_callbacks: CallbackRegistrar | None,
) -> WebModule:
    def register_services(services: ServiceRegistry) -> None:
        services.add(ADA_KPI_COLLECTOR_SERVICE_KEY, collector)
        services.add(ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY, polling_runtime)

    def register_middlewares(server: Flask, _services: ServiceRegistry) -> None:
        def ensure_collector_started() -> None:
            if request.path.startswith(_START_EXCLUDED_PATH_PREFIXES):
                return None
            polling_runtime.ensure_started()
            return None

        server.before_request(ensure_collector_started)

    return WebModule(
        name='ada-kpi-collector',
        register_services=register_services,
        register_middlewares=register_middlewares,
        register_callbacks=register_callbacks,
    )


def _create_callback_registrar(
    *,
    structure: ToolStructure,
    settings: KpiCollectorPresentationSettings,
) -> CallbackRegistrar:
    component_ids = tuple(
        component_kpi_store_id(structure.tool_key, component.key)
        for component in structure.components
    )

    def register_callbacks(dash_app: Dash, services: ServiceRegistry) -> None:
        outputs = tuple(Output(component_id, 'data') for component_id in component_ids)
        states = tuple(State(component_id, 'data') for component_id in component_ids)

        @dash_app.callback(
            *outputs,
            Output(settings.revision_store_id, 'data'),
            Input(settings.interval_id, 'n_intervals'),
            State(settings.revision_store_id, 'data'),
            *states,
        )
        def refresh_from_cache(
            _n_intervals: int,
            browser_revision: object,
            *browser_component_data: object,
        ):
            collector = services.require(ADA_KPI_COLLECTOR_SERVICE_KEY)
            component_updates, revision = resolve_kpi_collector_browser_update(
                collector,
                browser_revision=browser_revision,
                browser_component_data=browser_component_data,
            )
            return (*component_updates, revision)

    return register_callbacks


def _build_runtime_components(
    *,
    collector: KpiCollectorPresentationSource,
    settings: KpiCollectorPresentationSettings,
) -> tuple[Component, ...]:
    structure = collector.structure
    snapshot = collector.snapshot
    stores = {store.component_key: store for store in snapshot.stores}
    component_stores = tuple(
        dcc.Store(
            id=component_kpi_store_id(structure.tool_key, component.key),
            storage_type='memory',
            data=project_component_store_data(stores[component.key]),
        )
        for component in structure.components
    )
    return (
        dcc.Interval(
            id=settings.interval_id,
            interval=int(settings.refresh_interval_seconds * 1000),
            n_intervals=0,
        ),
        dcc.Store(
            id=settings.revision_store_id,
            storage_type='memory',
            data=snapshot.browser_revision,
        ),
        *component_stores,
    )


def _append_runtime_components(
    layout: Component,
    runtime_components: tuple[Component, ...],
) -> None:
    children = getattr(layout, 'children', None)
    if children is None:
        layout.children = list(runtime_components)
        return
    if isinstance(children, list):
        layout.children = [*children, *runtime_components]
        return
    if isinstance(children, tuple):
        layout.children = [*children, *runtime_components]
        return
    layout.children = [children, *runtime_components]
