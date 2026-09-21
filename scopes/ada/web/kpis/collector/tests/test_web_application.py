from __future__ import annotations

from pathlib import Path
from threading import Event

import pytest
from dash import html

from ada.web.components import build_empty_component_stores
from ada.web.kpis.collector import (
    ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
    KPI_COMPONENT_STORE_TYPE,
    AdaKpiCollectorPollingRuntime,
    KpiCollectorRefreshResult,
    KpiCollectorRefreshStatus,
    KpiCollectorSnapshot,
    KpiDeliveryReadError,
    attach_ada_kpi_collector,
)
from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from atlanticus.web.application import create_web_application
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.observability import (
    WEB_OBSERVABILITY_SERVICE_KEY,
    WebObservability,
    bind_web_external_sink,
)


class CollectorStub:
    def __init__(self, structure: ToolStructure) -> None:
        self.structure = structure
        self.snapshot = KpiCollectorSnapshot(build_empty_component_stores(structure))
        self.latest_error: Exception | None = None
        self.latest_calls = 0
        self.timeseries_calls = 0
        self.refreshed = Event()

    def refresh_latest(self) -> KpiCollectorRefreshResult:
        self.latest_calls += 1
        self.refreshed.set()
        if self.latest_error is not None:
            raise self.latest_error
        return KpiCollectorRefreshResult(KpiCollectorRefreshStatus.UNCHANGED, 'latest-r1')

    def refresh_timeseries(self) -> KpiCollectorRefreshResult:
        self.timeseries_calls += 1
        self.refreshed.set()
        return KpiCollectorRefreshResult(KpiCollectorRefreshStatus.UNCHANGED, 'timeseries-r1')


class CollectingSink:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


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


def _build_page_package(tmp_path: Path, name: str) -> str:
    package = tmp_path / name
    package.mkdir()
    (package / '__init__.py').write_text('', encoding='utf-8')
    (package / 'home.py').write_text(
        'from dash import html, register_page\n'
        "register_page(__name__, path='/', name='Home')\n"
        "layout = html.Div('Home')\n",
        encoding='utf-8',
    )
    return name


def _definition(tmp_path: Path, page_package: str) -> WebApplicationDefinition:
    return WebApplicationDefinition(
        import_name='test_kpi_collector_web',
        metadata=ApplicationMetadata(
            application_id='test-kpi-collector-web',
            display_name='Collector Test',
            version='0.1.0',
        ),
        publications_root=tmp_path / 'published',
        layout=lambda _services: html.Div(id='application-root'),
        page_packages=(page_package,),
    )


def _component_store_ids(value: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(value, dict):
        candidate = value.get('id')
        if isinstance(candidate, dict) and candidate.get('type') == KPI_COMPONENT_STORE_TYPE:
            found.append(candidate)
        for nested in value.values():
            found.extend(_component_store_ids(nested))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_component_store_ids(nested))
    return found


def test_attached_collector_uses_real_web_lifecycle_and_component_stores(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page_package = _build_page_package(tmp_path, 'test_kpi_collector_pages')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    collector = CollectorStub(_structure())
    definition = attach_ada_kpi_collector(_definition(tmp_path, page_package), collector)
    runtime = create_web_application(definition)
    polling_runtime = runtime.services.require(
        ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
        AdaKpiCollectorPollingRuntime,
    )
    client = runtime.server.test_client()

    assert runtime.services.require(WEB_OBSERVABILITY_SERVICE_KEY, WebObservability) is (
        runtime.observability
    )
    assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').status_code == 200
    assert not polling_runtime.is_running
    assert collector.latest_calls == 0
    assert collector.timeseries_calls == 0

    assert client.get('/').status_code == 200
    assert collector.refreshed.wait(1.0)
    assert collector.latest_calls > 0
    assert collector.timeseries_calls > 0

    layout_response = client.get('/_dash-layout')
    assert layout_response.status_code == 200
    ids = _component_store_ids(layout_response.get_json())
    assert ids == [
        {'type': KPI_COMPONENT_STORE_TYPE, 'tool': 'process', 'component': 'mine'},
        {'type': KPI_COMPONENT_STORE_TYPE, 'tool': 'process', 'component': 'plant'},
    ]

    polling_runtime.stop()


def test_attached_collector_reports_delivery_failure_through_framework_observability_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page_package = _build_page_package(tmp_path, 'test_kpi_collector_observability_pages')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    sink = CollectingSink()
    binding = bind_web_external_sink(sink)
    try:
        collector = CollectorStub(_structure())
        collector.latest_error = KpiDeliveryReadError('Could not read KPI delivery from Cosmos')
        runtime = create_web_application(
            attach_ada_kpi_collector(_definition(tmp_path, page_package), collector)
        )
        polling_runtime = runtime.services.require(
            ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
            AdaKpiCollectorPollingRuntime,
        )

        polling_runtime.poll_due(now=0.0)
        polling_runtime.poll_due(now=10.0)
    finally:
        binding.close()

    collector_events = [
        event for event in sink.events if event.name.startswith('web.kpi_collector.')
    ]
    assert len(collector_events) == 1
    assert collector_events[0].name == 'web.kpi_collector.delivery_unavailable'
    assert collector_events[0].context['source'] == 'latest'


def test_collector_attachment_rejects_duplicate_module(tmp_path: Path) -> None:
    collector = CollectorStub(_structure())
    definition = attach_ada_kpi_collector(
        _definition(tmp_path, 'unused_pages'),
        collector,
    )

    with pytest.raises(ValueError, match='already attached'):
        attach_ada_kpi_collector(definition, collector)
