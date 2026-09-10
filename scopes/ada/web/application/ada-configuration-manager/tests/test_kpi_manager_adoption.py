from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from dash.development.base_component import Component

from ada.web.application.configuration_manager import (
    KPI_WORKFLOW_SERVICE,
    KpiConfigurationManagerWorkflowAdapter,
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.kpis import (
    KPI_IMPORT_UPLOAD_ID,
    KPI_SAVE_BUTTON_ID,
)
from ada.web.kpis.configuration import KpiDestination, KpiDestinationCatalog
from ada.web.kpis.configuration.web.ids import ADD_BUTTON_ID
from atlanticus.web.manager import ManagerSurface
from atlanticus.web.services import ServiceRegistry

from .test_composition import dependencies


class DestinationProvider:
    def __init__(self, with_component: bool) -> None:
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


def _kpi_services():
    return SimpleNamespace(
        administration=SimpleNamespace(),
        projection_workflow=SimpleNamespace(),
    )


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


def _with_kpis(with_component: bool):
    return replace(
        dependencies(),
        kpis=_kpi_services(),
        kpi_destinations=DestinationProvider(with_component),
        kpis_source_name='KPI Source',
        kpis_projection_name='KPI Projection',
    )


def test_existing_surface_is_unchanged_without_kpi_injection() -> None:
    surface = ManagerSurface(build_configuration_manager_surface(dependencies()))
    assert tuple(module.key for module in surface.registry.modules) == (
        'users',
        'navigation',
        'tools',
    )


def test_kpi_is_fourth_configuration_module_when_injected() -> None:
    definition = build_configuration_manager_surface(_with_kpis(True))
    surface = ManagerSurface(definition)

    assert tuple(module.key for module in surface.registry.modules) == (
        'users',
        'navigation',
        'tools',
        'kpis',
    )

    kpis = definition.modules[-1]
    assert kpis.title == 'KPI'
    assert kpis.route == '/kpis'
    assert kpis.workflow_service == KPI_WORKFLOW_SERVICE
    assert kpis.access.view == 'kpis.manage'
    assert kpis.access.validate == 'kpis.manage'
    assert kpis.access.publish == 'kpis.manage'
    assert kpis.access.project == 'kpis.manage'


def test_kpi_uses_standard_import_and_browser_draft_controls() -> None:
    definition = build_configuration_manager_surface(_with_kpis(True))
    layout = definition.modules[-1].layout(None)
    nodes = _walk(layout)

    ids = {
        node.id
        for node in nodes
        if isinstance(getattr(node, 'id', None), str)
    }
    texts = {
        node.children
        for node in nodes
        if isinstance(getattr(node, 'children', None), str)
    }

    assert KPI_IMPORT_UPLOAD_ID in ids
    assert KPI_SAVE_BUTTON_ID in ids
    assert 'Fuente de verdad' in texts
    assert 'Proyección' in texts
    assert 'Guardar borrador' in texts


def test_kpi_creation_follows_tool_component_restriction() -> None:
    blocked = build_configuration_manager_surface(_with_kpis(False))
    allowed = build_configuration_manager_surface(_with_kpis(True))

    blocked_add = next(
        node
        for node in _walk(blocked.modules[-1].layout(None))
        if getattr(node, 'id', None) == ADD_BUTTON_ID
    )
    allowed_add = next(
        node
        for node in _walk(allowed.modules[-1].layout(None))
        if getattr(node, 'id', None) == ADD_BUTTON_ID
    )

    assert blocked_add.disabled is True
    assert allowed_add.disabled is False


def test_service_module_registers_kpi_workflow_adapter() -> None:
    definition = build_configuration_manager_surface(_with_kpis(True))
    service_module = next(
        module
        for module in definition.web_modules
        if module.name == 'ada-configuration-manager-services'
    )
    services = ServiceRegistry()
    assert service_module.register_services is not None
    service_module.register_services(services)

    assert isinstance(
        services.require(KPI_WORKFLOW_SERVICE),
        KpiConfigurationManagerWorkflowAdapter,
    )
