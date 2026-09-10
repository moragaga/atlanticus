from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from dash.development.base_component import Component

from ada.web.application.configuration_manager import (
    KPI_DEFINITION_WORKFLOW_SERVICE,
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.kpi_definitions import (
    KPI_DEFINITION_IMPORT_UPLOAD_ID,
    KPI_DEFINITION_SAVE_BUTTON_ID,
)
from ada.web.kpis.configuration import (
    KpiDestination,
    KpiDestinationCatalog,
)
from ada.web.kpis.definition import KpiDefinitionAuthorityCatalog
from ada.web.kpis.definition.web.ids import SEARCH_ID, STATUS_FILTER_ID
from atlanticus.web.manager import ManagerSurface

from .test_composition import dependencies


class Destinations:
    def load(self):
        return KpiDestinationCatalog(
            tool_projection_revision='tools-r1',
            destinations=(
                KpiDestination(
                    key='global_indicators',
                    display_name='Global Indicators',
                ),
                KpiDestination(key='time_status', display_name='Time Status'),
                KpiDestination(key='plant', display_name='Planta'),
            ),
        )


class Authority:
    def load(self):
        return KpiDefinitionAuthorityCatalog(
            kpi_configuration_revision='kpi-config-r1',
            kpi_keys=('availability', 'throughput'),
        )


def _services():
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


def _with_definition():
    return replace(
        dependencies(),
        kpis=_services(),
        kpi_destinations=Destinations(),
        kpi_definitions=_services(),
        kpi_definition_authority=Authority(),
        kpis_source_name='KPI Source',
        kpis_projection_name='KPI Projection',
        kpi_definitions_source_name='Definition Source',
        kpi_definitions_projection_name='Definition Projection',
    )


def test_definition_is_fifth_configuration_module() -> None:
    definition = build_configuration_manager_surface(_with_definition())
    surface = ManagerSurface(definition)

    assert tuple(module.key for module in surface.registry.modules) == (
        'users',
        'navigation',
        'tools',
        'kpis',
        'kpi-definitions',
    )

    module = definition.modules[-1]
    assert module.title == 'Definiciones KPI'
    assert module.route == '/kpi-definitions'
    assert module.workflow_service == KPI_DEFINITION_WORKFLOW_SERVICE
    assert module.access.view == 'kpis.manage'
    assert module.access.validate == 'kpis.manage'
    assert module.access.publish == 'kpis.manage'
    assert module.access.project == 'kpis.manage'


def test_definition_uses_standard_manager_controls_and_minimal_grid() -> None:
    definition = build_configuration_manager_surface(_with_definition())
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

    assert KPI_DEFINITION_IMPORT_UPLOAD_ID in ids
    assert KPI_DEFINITION_SAVE_BUTTON_ID in ids
    assert SEARCH_ID in ids
    assert STATUS_FILTER_ID in ids
    assert 'Fuente de verdad' in texts
    assert 'Proyección' in texts
    assert 'Guardar borrador' in texts


def test_definition_module_does_not_duplicate_shared_configuration_asset() -> None:
    surface = ManagerSurface(build_configuration_manager_surface(_with_definition()))
    layers = tuple(
        layer
        for web_module in surface.web_modules
        for layer in web_module.asset_layers
    )
    names = tuple(layer.name for layer in layers)
    orders = tuple(layer.load_order for layer in layers)

    assert names.count('ada_configuration') == 1
    assert names.count('ada_kpi_definition_editor') == 1
    assert len(names) == len(set(names))
    assert len(orders) == len(set(orders))


def test_definition_dependency_requires_kpi_configuration_module() -> None:
    with pytest.raises(
        ValueError,
        match='KPI Definition requires KPI Configuration',
    ):
        replace(
            dependencies(),
            kpi_definitions=_services(),
            kpi_definition_authority=Authority(),
        )
