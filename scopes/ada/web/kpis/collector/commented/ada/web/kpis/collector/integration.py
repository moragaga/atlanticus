# Integración Web del Collector. El layout publica Stores de componente y de sistema y un único
# callback copia snapshots desde el cache de proceso al navegador sin leer Cosmos inline.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from dash import Input, Output, State, dcc
from dash.development.base_component import Component
from flask import request

from ada.contracts.tools.structure import ToolStructure
from ada.web.kpis.collector.presentation import (
    KpiCollectorPresentationSettings,
    KpiCollectorPresentationSource,
    component_kpi_store_id,
    project_component_store_data,
    project_system_store_data,
    resolve_kpi_collector_browser_update,
    system_kpi_destination_keys,
    system_kpi_store_id,
)
from ada.web.kpis.collector.runtime import (
    AdaKpiCollectorPollingRuntime,
    KpiCollectorPollingSettings,
)
from atlanticus.web.models import WebApplicationDefinition
from atlanticus.web.modules import CallbackRegistrar, WebModule
from atlanticus.web.observability import WEB_OBSERVABILITY_SERVICE_KEY, WebObservability
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


def attach_ada_kpi_collector(
    definition: WebApplicationDefinition,
    collector: KpiCollectorPresentationSource,
    *,
    polling_settings: KpiCollectorPollingSettings | None = None,
    presentation_settings: KpiCollectorPresentationSettings | None = None,
) -> WebApplicationDefinition:
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('definition must be WebApplicationDefinition')
    if any(module.name == 'ada-kpi-collector' for module in definition.modules):
        raise ValueError('KPI collector is already attached to the application definition')
    integration = create_ada_kpi_collector_web_integration(
        collector,
        polling_settings=polling_settings,
        presentation_settings=presentation_settings,
    )
    return replace(
        definition,
        modules=(*definition.modules, integration.module),
        layout=integration.wrap_layout(definition.layout),
    )


def create_ada_kpi_collector_module(
    collector: object,
    *,
    polling_settings: KpiCollectorPollingSettings | None = None,
) -> WebModule:
    return _create_module(
        collector=collector,
        polling_settings=polling_settings,
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
    register_callbacks = _create_callback_registrar(
        structure=collector.structure,
        settings=resolved_presentation_settings,
    )
    return AdaKpiCollectorWebIntegration(
        module=_create_module(
            collector=collector,
            polling_settings=polling_settings,
            register_callbacks=register_callbacks,
        ),
        collector=collector,
        presentation_settings=resolved_presentation_settings,
    )


def _create_module(
    *,
    collector: object,
    polling_settings: KpiCollectorPollingSettings | None,
    register_callbacks: CallbackRegistrar | None,
) -> WebModule:
    def register_services(services: ServiceRegistry) -> None:
        observability = services.require(WEB_OBSERVABILITY_SERVICE_KEY, WebObservability)
        polling_runtime = AdaKpiCollectorPollingRuntime(
            collector,
            observability=observability,
            settings=polling_settings,
        )
        services.add(ADA_KPI_COLLECTOR_SERVICE_KEY, collector)
        services.add(ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY, polling_runtime)

    def register_middlewares(server: Flask, services: ServiceRegistry) -> None:
        polling_runtime = services.require(
            ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
            AdaKpiCollectorPollingRuntime,
        )

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
        requires_services=(WEB_OBSERVABILITY_SERVICE_KEY,),
    )


# El callback conserva un único revision Store y separa los State por identidad solo al invocar la
# proyección. Component y system outputs avanzan juntos en la misma ejecución.
def _create_callback_registrar(
    *,
    structure: ToolStructure,
    settings: KpiCollectorPresentationSettings,
) -> CallbackRegistrar:
    component_ids = tuple(
        component_kpi_store_id(structure.tool_key, component.key)
        for component in structure.components
    )
    system_ids = tuple(
        system_kpi_store_id(structure.tool_key, destination_key)
        for destination_key in system_kpi_destination_keys(structure)
    )

    def register_callbacks(dash_app: Dash, services: ServiceRegistry) -> None:
        outputs = tuple(Output(store_id, 'data') for store_id in (*component_ids, *system_ids))
        states = tuple(State(store_id, 'data') for store_id in (*component_ids, *system_ids))
        component_count = len(component_ids)

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
            *browser_store_data: object,
        ):
            collector = services.require(ADA_KPI_COLLECTOR_SERVICE_KEY)
            component_updates, system_updates, revision = resolve_kpi_collector_browser_update(
                collector,
                browser_revision=browser_revision,
                browser_component_data=browser_store_data[:component_count],
                browser_system_data=browser_store_data[component_count:],
            )
            return (*component_updates, *system_updates, revision)

    return register_callbacks


# Los System Stores se materializan junto a los Component Stores. Su identidad usa destination para
# evitar convertir global_indicators o time_status en componentes ficticios del Tool.
def _build_runtime_components(
    *,
    collector: KpiCollectorPresentationSource,
    settings: KpiCollectorPresentationSettings,
) -> tuple[Component, ...]:
    structure = collector.structure
    snapshot = collector.snapshot
    component_stores = {store.component_key: store for store in snapshot.stores}
    system_stores = {store.destination_key: store for store in snapshot.system_stores}
    component_store_components = tuple(
        dcc.Store(
            id=component_kpi_store_id(structure.tool_key, component.key),
            storage_type='memory',
            data=project_component_store_data(component_stores[component.key]),
        )
        for component in structure.components
    )
    system_store_components = tuple(
        dcc.Store(
            id=system_kpi_store_id(structure.tool_key, destination_key),
            storage_type='memory',
            data=project_system_store_data(system_stores[destination_key]),
        )
        for destination_key in system_kpi_destination_keys(structure)
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
        *component_store_components,
        *system_store_components,
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
