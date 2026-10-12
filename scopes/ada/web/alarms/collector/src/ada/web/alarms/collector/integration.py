from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from dash import Input, Output, State, dcc
from dash.development.base_component import Component
from flask import request

from ada.web.alarms.collector.collector import AdaAlarmCollector
from ada.web.alarms.collector.presentation import (
    AlarmCollectorPresentationSettings,
    alarm_live_store_id,
    project_alarm_live_store,
    resolve_alarm_live_browser_update,
)
from ada.web.alarms.collector.runtime import (
    AdaAlarmCollectorPollingRuntime,
    AlarmCollectorPollingSettings,
)
from atlanticus.web.models import WebApplicationDefinition
from atlanticus.web.modules import WebModule
from atlanticus.web.observability import WEB_OBSERVABILITY_SERVICE_KEY, WebObservability
from atlanticus.web.services import ServiceRegistry

if TYPE_CHECKING:
    from dash import Dash
    from flask import Flask

ADA_ALARM_COLLECTOR_SERVICE_KEY = 'ada.alarm.collector'
ADA_ALARM_COLLECTOR_RUNTIME_SERVICE_KEY = 'ada.alarm.collector.runtime'
_EXCLUDED_START_PATHS = ('/health/', '/assets/', '/.auth/')
LayoutFactory = Callable[..., object]


@dataclass(frozen=True, slots=True)
class AdaAlarmCollectorWebIntegration:
    module: WebModule
    collector: AdaAlarmCollector
    presentation_settings: AlarmCollectorPresentationSettings

    def wrap_layout(self, layout: LayoutFactory) -> LayoutFactory:
        if not callable(layout):
            raise TypeError('Alarm collector layout must be callable')

        def wrapped(*args: object, **kwargs: object) -> Component:
            resolved = layout(*args, **kwargs)
            if not isinstance(resolved, Component):
                raise TypeError('Alarm collector requires a Dash Component layout')
            snapshot = self.collector.snapshot
            components = (
                dcc.Interval(
                    id=self.presentation_settings.interval_id,
                    interval=int(self.presentation_settings.refresh_interval_seconds * 1000),
                    n_intervals=0,
                ),
                dcc.Store(
                    id=alarm_live_store_id(self.collector.tool_key),
                    storage_type='memory',
                    data=project_alarm_live_store(snapshot),
                ),
            )
            children = getattr(resolved, 'children', None)
            if children is None:
                resolved.children = list(components)
            elif isinstance(children, (list, tuple)):
                resolved.children = [*children, *components]
            else:
                resolved.children = [children, *components]
            return resolved

        return wrapped


def create_ada_alarm_collector_web_integration(
    collector: AdaAlarmCollector, *,
    polling_settings: AlarmCollectorPollingSettings | None = None,
    presentation_settings: AlarmCollectorPresentationSettings | None = None,
) -> AdaAlarmCollectorWebIntegration:
    if not isinstance(collector, AdaAlarmCollector):
        raise TypeError('Alarm Web integration requires AdaAlarmCollector')
    settings = presentation_settings or AlarmCollectorPresentationSettings()
    if not isinstance(settings, AlarmCollectorPresentationSettings):
        raise TypeError('Alarm presentation settings are invalid')

    def register_services(services: ServiceRegistry) -> None:
        observability = services.require(WEB_OBSERVABILITY_SERVICE_KEY, WebObservability)
        runtime = AdaAlarmCollectorPollingRuntime(
            collector, observability=observability, settings=polling_settings,
        )
        services.add(ADA_ALARM_COLLECTOR_SERVICE_KEY, collector)
        services.add(ADA_ALARM_COLLECTOR_RUNTIME_SERVICE_KEY, runtime)

    def register_middlewares(server: Flask, services: ServiceRegistry) -> None:
        runtime = services.require(
            ADA_ALARM_COLLECTOR_RUNTIME_SERVICE_KEY, AdaAlarmCollectorPollingRuntime,
        )

        def ensure_collector_started() -> None:
            if not request.path.startswith(_EXCLUDED_START_PATHS):
                runtime.ensure_started()

        server.before_request(ensure_collector_started)

    def register_callbacks(dash_app: Dash, services: ServiceRegistry) -> None:
        store_id = alarm_live_store_id(collector.tool_key)

        @dash_app.callback(
            Output(store_id, 'data'),
            Input(settings.interval_id, 'n_intervals'),
            State(store_id, 'data'),
        )
        def refresh_from_cache(_interval: int, browser_data: object):
            source = services.require(ADA_ALARM_COLLECTOR_SERVICE_KEY, AdaAlarmCollector)
            return resolve_alarm_live_browser_update(
                source.snapshot, browser_data=browser_data,
            )

    return AdaAlarmCollectorWebIntegration(
        module=WebModule(
            name='ada-alarm-collector',
            register_services=register_services,
            register_middlewares=register_middlewares,
            register_callbacks=register_callbacks,
            requires_services=(WEB_OBSERVABILITY_SERVICE_KEY,),
        ),
        collector=collector,
        presentation_settings=settings,
    )


def attach_ada_alarm_collector(
    definition: WebApplicationDefinition,
    collector: AdaAlarmCollector, *,
    polling_settings: AlarmCollectorPollingSettings | None = None,
    presentation_settings: AlarmCollectorPresentationSettings | None = None,
) -> WebApplicationDefinition:
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('Alarm collector requires WebApplicationDefinition')
    if any(module.name == 'ada-alarm-collector' for module in definition.modules):
        raise ValueError('Alarm collector is already attached')
    integration = create_ada_alarm_collector_web_integration(
        collector, polling_settings=polling_settings,
        presentation_settings=presentation_settings,
    )
    return replace(
        definition,
        modules=(*definition.modules, integration.module),
        layout=integration.wrap_layout(definition.layout),
    )
