from __future__ import annotations

from dash import html, no_update

from ada.web.components import ComponentStoreSnapshot, build_empty_component_stores
from ada.web.kpis.collector import (
    DEFAULT_KPI_BROWSER_REFRESH_INTERVAL_SECONDS,
    KPI_COMPONENT_STORE_TYPE,
    AdaKpiCollectorWebIntegration,
    ComponentKpiData,
    ComponentLatestKpiData,
    ComponentTimeseriesKpiData,
    KpiCollectorPresentationSettings,
    KpiCollectorSnapshot,
    component_kpi_store_id,
    create_ada_kpi_collector_web_integration,
    project_component_store_data,
    resolve_kpi_collector_browser_update,
)
from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent


class PresentationCollectorStub:
    def __init__(self, structure: ToolStructure) -> None:
        self.structure = structure
        self.snapshot = KpiCollectorSnapshot(build_empty_component_stores(structure))
        self.refresh_latest_calls = 0
        self.refresh_timeseries_calls = 0

    def refresh_latest(self):
        self.refresh_latest_calls += 1

    def refresh_timeseries(self):
        self.refresh_timeseries_calls += 1


class ServiceRegistryStub:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def add(self, name: str, service: object) -> None:
        self.values[name] = service

    def require(self, name: str) -> object:
        return self.values[name]


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
                'value_kind': 'integer',
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
    return KpiCollectorSnapshot(
        stores=stores,
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


def test_component_store_id_is_derived_from_tool_and_component_identity() -> None:
    assert component_kpi_store_id('process', 'mine') == {
        'type': KPI_COMPONENT_STORE_TYPE,
        'tool': 'process',
        'component': 'mine',
    }


def test_layout_wrapper_mounts_one_browser_store_per_tool_component() -> None:
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
    assert children[3].data == {
        'tool_key': 'process',
        'component_key': 'mine',
        'latest': None,
        'timeseries': None,
    }


def test_component_store_projection_is_json_serializable_and_contains_both_contracts() -> None:
    store = ComponentStoreSnapshot(
        tool_key='process',
        component_key='mine',
        payload=ComponentKpiData(
            latest=_latest(7, 'latest-r1'),
            timeseries=_timeseries('timeseries-r1'),
        ),
    )

    projected = project_component_store_data(store)

    assert projected['tool_key'] == 'process'
    assert projected['component_key'] == 'mine'
    assert projected['latest']['values']['rate']['value'] == 7
    assert projected['timeseries']['series']['rate']['values'] == [1, 2, 3]


def test_browser_update_reads_cache_without_triggering_collector_refresh() -> None:
    structure = _structure()
    collector = PresentationCollectorStub(structure)
    collector.snapshot = _snapshot(
        structure,
        latest_revision='latest-r1',
        latest_watermark_utc='2026-09-20T20:00:00+00:00',
        latest_configuration_revision='config-r1',
        mine_payload=ComponentKpiData(latest=_latest(7, 'latest-r1')),
    )

    updates, revision = resolve_kpi_collector_browser_update(
        collector,
        browser_revision=None,
        browser_component_data=(None, None),
    )

    assert updates[0]['latest']['values']['rate']['value'] == 7
    assert updates[1]['latest'] is None
    assert revision['latest']['revision'] == 'latest-r1'
    assert collector.refresh_latest_calls == 0
    assert collector.refresh_timeseries_calls == 0


def test_unchanged_browser_revision_returns_no_update_for_every_component() -> None:
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

    updates, revision = resolve_kpi_collector_browser_update(
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
    )

    assert updates == (no_update, no_update)
    assert revision is no_update


def test_new_latest_preserves_newer_browser_timeseries_from_another_worker() -> None:
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

    updates, revision = resolve_kpi_collector_browser_update(
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
    )

    assert updates[0]['latest']['values']['rate']['value'] == 8
    assert updates[0]['timeseries'] is browser_timeseries
    assert revision['latest']['revision'] == 'latest-r2'
    assert revision['timeseries']['revision'] == 'timeseries-r2'


def test_new_latest_configuration_clears_incompatible_browser_timeseries() -> None:
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

    updates, revision = resolve_kpi_collector_browser_update(
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
    )

    assert updates[0]['timeseries'] is None
    assert updates[1]['timeseries'] is None
    assert revision['latest']['configuration_revision'] == 'config-r2'
    assert revision['timeseries'] is None


def test_callback_registers_one_output_per_tool_component_and_uses_cache_only() -> None:
    structure = _structure()
    collector = PresentationCollectorStub(structure)
    collector.snapshot = _snapshot(
        structure,
        latest_revision='latest-r1',
        latest_watermark_utc='2026-09-20T20:00:00+00:00',
        latest_configuration_revision='config-r1',
        mine_payload=ComponentKpiData(latest=_latest(7, 'latest-r1')),
    )
    integration = create_ada_kpi_collector_web_integration(collector)
    services = ServiceRegistryStub()
    dash_app = DashStub()
    integration.module.register_services(services)
    integration.module.register_callbacks(dash_app, services)

    result = dash_app.callback_function(1, None, None, None)

    assert len(result) == 3
    assert result[0]['component_key'] == 'mine'
    assert result[1]['component_key'] == 'plant'
    assert result[2]['latest']['revision'] == 'latest-r1'
    assert collector.refresh_latest_calls == 0
    assert collector.refresh_timeseries_calls == 0
