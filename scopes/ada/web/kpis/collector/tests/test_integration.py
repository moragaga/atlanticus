from __future__ import annotations

import logging

from dash import html, no_update

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada.web.components import ComponentStoreSnapshot, build_empty_component_stores
from ada.web.kpis.collector import (
    DEFAULT_KPI_BROWSER_REFRESH_INTERVAL_SECONDS,
    KPI_COMPONENT_STORE_TYPE,
    KPI_SYSTEM_STORE_TYPE,
    AdaKpiCollectorWebIntegration,
    ComponentKpiData,
    ComponentLatestKpiData,
    ComponentTimeseriesKpiData,
    KpiCollectorPresentationSettings,
    KpiCollectorSnapshot,
    SystemKpiStoreSnapshot,
    component_kpi_store_id,
    create_ada_kpi_collector_web_integration,
    project_component_store_data,
    project_system_store_data,
    resolve_kpi_collector_browser_update,
    system_kpi_store_id,
)
from atlanticus.web.observability import WEB_OBSERVABILITY_SERVICE_KEY, WebObservability
from atlanticus.web.services import ServiceRegistry


class PresentationCollectorStub:
    def __init__(self, structure: ToolStructure) -> None:
        self.structure = structure
        self.snapshot = KpiCollectorSnapshot(
            build_empty_component_stores(structure),
            system_stores=_empty_system_stores(structure),
        )
        self.refresh_latest_calls = 0
        self.refresh_timeseries_calls = 0

    def refresh_latest(self):
        self.refresh_latest_calls += 1

    def refresh_timeseries(self):
        self.refresh_timeseries_calls += 1


class DashStub:
    def __init__(self) -> None:
        self.callback_function = None
        self.callback_args = ()

    def callback(self, *args, **_kwargs):
        self.callback_args = args

        def register(function):
            self.callback_function = function
            return function

        return register


def _structure() -> ToolStructure:
    return ToolStructure(
        tool_key='process',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.MINE,
        center_component_key='mine',
        components=(
            ToolComponent(
                key='mine',
                display_name='Mine',
                subcomponents=(ToolSubcomponent(key='mine_phase', display_name='Mine Phase'),),
            ),
            ToolComponent(
                key='plant',
                display_name='Plant',
                subcomponents=(ToolSubcomponent(key='plant_phase', display_name='Plant Phase'),),
            ),
        ),
    )


def _empty_system_stores(structure: ToolStructure) -> tuple[SystemKpiStoreSnapshot, ...]:
    return tuple(
        SystemKpiStoreSnapshot(structure.tool_key, key)
        for key in ('global_indicators', 'time_status')
    )


def _latest(value: int, revision: str) -> ComponentLatestKpiData:
    return ComponentLatestKpiData(
        manifest={
            'revision': revision,
            'configuration_revision': 'config-r1',
            'watermark_utc': '2026-09-20T20:00:00+00:00',
        },
        values={
            'rate': {
                'status': 'ok',
                'value_kind': 'value',
                'value': value,
            }
        },
    )


def _timeseries(revision: str) -> ComponentTimeseriesKpiData:
    return ComponentTimeseriesKpiData(
        manifest={
            'revision': revision,
            'configuration_revision': 'config-r1',
        },
        end_utc='2026-09-20T20:00:00+00:00',
        step_seconds=120,
        series={
            'rate': {
                'hours': 1,
                'start_utc': '2026-09-20T19:00:00+00:00',
                'end_utc': '2026-09-20T20:00:00+00:00',
                'value_type': 'integer',
                'values': (1, 2, 3),
            }
        },
    )


def _snapshot(
    structure: ToolStructure,
    *,
    latest_revision: str | None = None,
    latest_watermark_utc: str | None = None,
    latest_configuration_revision: str | None = None,
    timeseries_revision: str | None = None,
    timeseries_end_utc: str | None = None,
    timeseries_configuration_revision: str | None = None,
    mine_payload: ComponentKpiData | None = None,
    plant_payload: ComponentKpiData | None = None,
    global_payload: ComponentKpiData | None = None,
    time_status_payload: ComponentKpiData | None = None,
) -> KpiCollectorSnapshot:
    payloads = {'mine': mine_payload, 'plant': plant_payload}
    stores = tuple(
        ComponentStoreSnapshot(
            tool_key=structure.tool_key,
            component_key=component.key,
            payload=payloads[component.key],
        )
        for component in structure.components
    )
    system_stores = (
        SystemKpiStoreSnapshot(structure.tool_key, 'global_indicators', global_payload),
        SystemKpiStoreSnapshot(structure.tool_key, 'time_status', time_status_payload),
    )
    return KpiCollectorSnapshot(
        stores=stores,
        system_stores=system_stores,
        latest_revision=latest_revision,
        latest_watermark_utc=latest_watermark_utc,
        latest_configuration_revision=latest_configuration_revision,
        timeseries_revision=timeseries_revision,
        timeseries_end_utc=timeseries_end_utc,
        timeseries_configuration_revision=timeseries_configuration_revision,
    )


def test_browser_refresh_interval_is_independent_and_configurable() -> None:
    default_settings = KpiCollectorPresentationSettings()
    custom_settings = KpiCollectorPresentationSettings(refresh_interval_seconds=3)

    assert (
        default_settings.refresh_interval_seconds
        == DEFAULT_KPI_BROWSER_REFRESH_INTERVAL_SECONDS
        == 10.0
    )
    assert custom_settings.refresh_interval_seconds == 3


def test_store_ids_keep_component_and_system_namespaces_separate() -> None:
    assert component_kpi_store_id('process', 'mine') == {
        'type': KPI_COMPONENT_STORE_TYPE,
        'tool': 'process',
        'component': 'mine',
    }
    assert system_kpi_store_id('process', 'global_indicators') == {
        'type': KPI_SYSTEM_STORE_TYPE,
        'tool': 'process',
        'destination': 'global_indicators',
    }


def test_layout_wrapper_mounts_component_and_system_stores() -> None:
    collector = PresentationCollectorStub(_structure())
    integration = create_ada_kpi_collector_web_integration(collector)
    wrapped = integration.wrap_layout(
        lambda: html.Div(html.Div(id='existing'), id='application-root')
    )

    layout = wrapped()

    assert isinstance(integration, AdaKpiCollectorWebIntegration)
    assert layout.id == 'application-root'
    children = tuple(layout.children)
    assert children[0].id == 'existing'
    assert children[1].id == 'ada-kpi-collector-refresh'
    assert children[2].id == 'ada-kpi-collector-browser-revision'
    assert children[3].id == component_kpi_store_id('process', 'mine')
    assert children[4].id == component_kpi_store_id('process', 'plant')
    assert children[5].id == system_kpi_store_id('process', 'global_indicators')
    assert children[6].id == system_kpi_store_id('process', 'time_status')
    assert children[5].data == {
        'tool_key': 'process',
        'destination_key': 'global_indicators',
        'latest': None,
        'timeseries': None,
    }


def test_store_projection_is_json_serializable_for_both_store_families() -> None:
    payload = ComponentKpiData(
        latest=_latest(7, 'latest-r1'),
        timeseries=_timeseries('timeseries-r1'),
    )
    component = ComponentStoreSnapshot('process', 'mine', payload)
    system = SystemKpiStoreSnapshot('process', 'global_indicators', payload)

    projected_component = project_component_store_data(component)
    projected_system = project_system_store_data(system)

    assert projected_component['component_key'] == 'mine'
    assert projected_system['destination_key'] == 'global_indicators'
    assert projected_component['latest']['values']['rate']['value'] == 7
    assert projected_system['timeseries']['series']['rate']['values'] == [1, 2, 3]


def test_browser_update_reads_cache_without_triggering_collector_refresh() -> None:
    structure = _structure()
    collector = PresentationCollectorStub(structure)
    collector.snapshot = _snapshot(
        structure,
        latest_revision='latest-r1',
        latest_watermark_utc='2026-09-20T20:00:00+00:00',
        latest_configuration_revision='config-r1',
        mine_payload=ComponentKpiData(latest=_latest(7, 'latest-r1')),
        global_payload=ComponentKpiData(latest=_latest(9, 'latest-r1')),
    )

    component_updates, system_updates, revision = resolve_kpi_collector_browser_update(
        collector,
        browser_revision=None,
        browser_component_data=(None, None),
        browser_system_data=(None, None),
    )

    assert component_updates[0]['latest']['values']['rate']['value'] == 7
    assert component_updates[1]['latest'] is None
    assert system_updates[0]['latest']['values']['rate']['value'] == 9
    assert system_updates[1]['latest'] is None
    assert revision['latest']['revision'] == 'latest-r1'
    assert collector.refresh_latest_calls == 0
    assert collector.refresh_timeseries_calls == 0


def test_unchanged_browser_revision_returns_no_update_for_every_store() -> None:
    structure = _structure()
    collector = PresentationCollectorStub(structure)
    collector.snapshot = _snapshot(
        structure,
        latest_revision='latest-r1',
        latest_watermark_utc='2026-09-20T20:00:00+00:00',
        latest_configuration_revision='config-r1',
        mine_payload=ComponentKpiData(latest=_latest(7, 'latest-r1')),
    )
    browser_revision = collector.snapshot.browser_revision

    component_updates, system_updates, revision = resolve_kpi_collector_browser_update(
        collector,
        browser_revision=browser_revision,
        browser_component_data=(
            {
                'tool_key': 'process',
                'component_key': 'mine',
                'latest': {'preserved': True},
                'timeseries': None,
            },
            {
                'tool_key': 'process',
                'component_key': 'plant',
                'latest': None,
                'timeseries': None,
            },
        ),
        browser_system_data=(
            {
                'tool_key': 'process',
                'destination_key': 'global_indicators',
                'latest': None,
                'timeseries': None,
            },
            {
                'tool_key': 'process',
                'destination_key': 'time_status',
                'latest': None,
                'timeseries': None,
            },
        ),
    )

    assert component_updates == (no_update, no_update)
    assert system_updates == (no_update, no_update)
    assert revision is no_update


def test_new_latest_preserves_newer_browser_timeseries_for_all_store_families() -> None:
    structure = _structure()
    collector = PresentationCollectorStub(structure)
    collector.snapshot = _snapshot(
        structure,
        latest_revision='latest-r2',
        latest_watermark_utc='2026-09-20T20:01:00+00:00',
        latest_configuration_revision='config-r1',
        timeseries_revision='timeseries-r1',
        timeseries_end_utc='2026-09-20T20:00:00+00:00',
        timeseries_configuration_revision='config-r1',
        mine_payload=ComponentKpiData(
            latest=_latest(8, 'latest-r2'),
            timeseries=_timeseries('timeseries-r1'),
        ),
        global_payload=ComponentKpiData(
            latest=_latest(9, 'latest-r2'),
            timeseries=_timeseries('timeseries-r1'),
        ),
    )
    browser_revision = {
        'latest': {
            'revision': 'latest-r1',
            'watermark_utc': '2026-09-20T20:00:00+00:00',
            'configuration_revision': 'config-r1',
        },
        'timeseries': {
            'revision': 'timeseries-r2',
            'end_utc': '2026-09-20T20:02:00+00:00',
            'configuration_revision': 'config-r1',
        },
    }
    browser_timeseries = {'revision': 'timeseries-r2', 'preserved': True}

    component_updates, system_updates, revision = resolve_kpi_collector_browser_update(
        collector,
        browser_revision=browser_revision,
        browser_component_data=(
            {
                'tool_key': 'process',
                'component_key': 'mine',
                'latest': {'revision': 'latest-r1'},
                'timeseries': browser_timeseries,
            },
            {
                'tool_key': 'process',
                'component_key': 'plant',
                'latest': None,
                'timeseries': None,
            },
        ),
        browser_system_data=(
            {
                'tool_key': 'process',
                'destination_key': 'global_indicators',
                'latest': {'revision': 'latest-r1'},
                'timeseries': browser_timeseries,
            },
            {
                'tool_key': 'process',
                'destination_key': 'time_status',
                'latest': None,
                'timeseries': None,
            },
        ),
    )

    assert component_updates[0]['latest']['values']['rate']['value'] == 8
    assert component_updates[0]['timeseries'] is browser_timeseries
    assert system_updates[0]['latest']['values']['rate']['value'] == 9
    assert system_updates[0]['timeseries'] is browser_timeseries
    assert revision['latest']['revision'] == 'latest-r2'
    assert revision['timeseries']['revision'] == 'timeseries-r2'


def test_new_latest_configuration_clears_incompatible_browser_timeseries_everywhere() -> None:
    structure = _structure()
    collector = PresentationCollectorStub(structure)
    collector.snapshot = _snapshot(
        structure,
        latest_revision='latest-r2',
        latest_watermark_utc='2026-09-20T20:01:00+00:00',
        latest_configuration_revision='config-r2',
        mine_payload=ComponentKpiData(latest=_latest(8, 'latest-r2')),
    )
    browser_revision = {
        'latest': {
            'revision': 'latest-r1',
            'watermark_utc': '2026-09-20T20:00:00+00:00',
            'configuration_revision': 'config-r1',
        },
        'timeseries': {
            'revision': 'timeseries-r1',
            'end_utc': '2026-09-20T20:00:00+00:00',
            'configuration_revision': 'config-r1',
        },
    }

    component_updates, system_updates, revision = resolve_kpi_collector_browser_update(
        collector,
        browser_revision=browser_revision,
        browser_component_data=(
            {
                'tool_key': 'process',
                'component_key': 'mine',
                'latest': {'revision': 'latest-r1'},
                'timeseries': {'revision': 'timeseries-r1'},
            },
            {
                'tool_key': 'process',
                'component_key': 'plant',
                'latest': None,
                'timeseries': {'revision': 'timeseries-r1'},
            },
        ),
        browser_system_data=(
            {
                'tool_key': 'process',
                'destination_key': 'global_indicators',
                'latest': None,
                'timeseries': {'revision': 'timeseries-r1'},
            },
            {
                'tool_key': 'process',
                'destination_key': 'time_status',
                'latest': None,
                'timeseries': {'revision': 'timeseries-r1'},
            },
        ),
    )

    assert all(update['timeseries'] is None for update in component_updates)
    assert all(update['timeseries'] is None for update in system_updates)
    assert revision['latest']['configuration_revision'] == 'config-r2'
    assert revision['timeseries'] is None


def test_callback_registers_outputs_for_components_systems_and_revision() -> None:
    structure = _structure()
    collector = PresentationCollectorStub(structure)
    collector.snapshot = _snapshot(
        structure,
        latest_revision='latest-r1',
        latest_watermark_utc='2026-09-20T20:00:00+00:00',
        latest_configuration_revision='config-r1',
        mine_payload=ComponentKpiData(latest=_latest(7, 'latest-r1')),
        global_payload=ComponentKpiData(latest=_latest(9, 'latest-r1')),
    )
    integration = create_ada_kpi_collector_web_integration(collector)
    services = ServiceRegistry()
    services.add(
        WEB_OBSERVABILITY_SERVICE_KEY,
        WebObservability(
            application='test-kpi-collector',
            logger=logging.getLogger('test.kpi.collector'),
            json_output=False,
        ),
    )
    dash_app = DashStub()
    integration.module.register_services(services)
    integration.module.register_callbacks(dash_app, services)

    result = dash_app.callback_function(1, None, None, None, None, None)

    assert len(result) == 5
    assert result[0]['component_key'] == 'mine'
    assert result[1]['component_key'] == 'plant'
    assert result[2]['destination_key'] == 'global_indicators'
    assert result[3]['destination_key'] == 'time_status'
    assert result[4]['latest']['revision'] == 'latest-r1'
    assert collector.refresh_latest_calls == 0
    assert collector.refresh_timeseries_calls == 0
