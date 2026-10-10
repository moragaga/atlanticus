from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada.web.kpis.collector import (
    AdaKpiCollector,
    ComponentKpiData,
    CosmosKpiDeliveryReader,
    KpiCollectorContractError,
    KpiCollectorRefreshStatus,
)


class CosmosClientStub:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, str, str], dict[str, object]] = {}
        self.calls: list[tuple[str, str, str, bool]] = []

    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        include_metadata: bool = False,
    ) -> dict[str, object] | None:
        self.calls.append((container_name, item_id, str(partition_key), include_metadata))
        value = self.documents.get((container_name, item_id, str(partition_key)))
        return None if value is None else deepcopy(value)


TOOL_REVISION = 'tool-r1'
CONFIGURATION_REVISION = 'kpis-r1'


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
                subcomponents=(
                    ToolSubcomponent(key='loading', display_name='Loading'),
                    ToolSubcomponent(key='hauling', display_name='Hauling'),
                ),
            ),
            ToolComponent(
                key='plant',
                display_name='Plant',
                subcomponents=(ToolSubcomponent(key='crushing', display_name='Crushing'),),
            ),
        ),
    )


def _latest(
    *,
    revision: str = 'latest-r1',
    configuration_revision: str = CONFIGURATION_REVISION,
    tool_revision: str = TOOL_REVISION,
    watermark: datetime | None = None,
) -> dict[str, object]:
    watermark = watermark or datetime(2026, 9, 20, 22, 0, tzinfo=UTC)
    return {
        'id': 'latest',
        'partition_id': 'kpis',
        'document_type': 'ada_kpi_latest_delivery',
        'manifest': {
            'schema_version': 2,
            'revision': revision,
            'configuration_revision': configuration_revision,
            'tool_projection_revision': tool_revision,
            'watermark_utc': _iso(watermark),
            'published_at_utc': _iso(watermark + timedelta(seconds=5)),
        },
        'destinations': {
            'global_indicators': {
                'system_kpi': {
                    'status': 'ok',
                    'value_kind': 'value',
                    'value': str(99.0),
                    'value_type': 'text',
                    'parsed_value': str(99.0),
                },
            },
            'mine': {
                'mine_rate': {
                    'status': 'ok',
                    'value_kind': 'value',
                    'value': str(42.0),
                    'value_type': 'text',
                    'parsed_value': str(42.0),
                },
            },
        },
    }


def _timeseries(
    *,
    revision: str = 'timeseries-r1',
    configuration_revision: str = CONFIGURATION_REVISION,
    tool_revision: str = TOOL_REVISION,
    end: datetime | None = None,
) -> dict[str, object]:
    end = end or datetime(2026, 9, 20, 22, 0, tzinfo=UTC)
    start = end - timedelta(hours=1)
    values = [float(index) for index in range(30)]
    return {
        'id': 'timeseries',
        'partition_id': 'kpis',
        'document_type': 'ada_kpi_timeseries_delivery',
        'manifest': {
            'schema_version': 2,
            'revision': revision,
            'configuration_revision': configuration_revision,
            'tool_projection_revision': tool_revision,
            'historian_revision': 'historian-r1',
            'published_at_utc': _iso(end + timedelta(seconds=5)),
        },
        'end_utc': _iso(end),
        'step_seconds': 120,
        'destinations': {
            'time_status': ['system_series'],
            'mine': ['mine_rate'],
            'plant': ['plant_rate'],
        },
        'series': {
            'system_series': _series(start, end, values),
            'mine_rate': _series(start, end, values),
            'plant_rate': _series(start, end, values),
        },
    }


def _series(start: datetime, end: datetime, values: list[float]) -> dict[str, object]:
    return {
        'hours': 1,
        'start_utc': _iso(start),
        'end_utc': _iso(end),
        'value_type': 'float',
        'values': values,
    }


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def _collector(client: CosmosClientStub) -> AdaKpiCollector:
    return AdaKpiCollector(
        structure=_structure(),
        tool_projection_revision=TOOL_REVISION,
        reader=CosmosKpiDeliveryReader(client),
    )


def _put_latest(client: CosmosClientStub, document: dict[str, object]) -> None:
    client.documents[('ada-kpi-latest-delivery', 'latest', 'kpis')] = document


def _put_timeseries(client: CosmosClientStub, document: dict[str, object]) -> None:
    client.documents[('ada-kpi-timeseries-delivery', 'timeseries', 'kpis')] = document


def _store(collector: AdaKpiCollector, component_key: str):
    return next(store for store in collector.stores if store.component_key == component_key)


def _system_store(collector: AdaKpiCollector, destination_key: str):
    return next(
        store for store in collector.system_stores if store.destination_key == destination_key
    )


def test_reader_uses_frozen_delivery_item_addresses() -> None:
    client = CosmosClientStub()
    reader = CosmosKpiDeliveryReader(client)

    assert reader.read_latest() is None
    assert reader.read_timeseries() is None
    assert client.calls == [
        ('ada-kpi-latest-delivery', 'latest', 'kpis', False),
        ('ada-kpi-timeseries-delivery', 'timeseries', 'kpis', False),
    ]


def test_collector_creates_component_and_system_store_families() -> None:
    collector = _collector(CosmosClientStub())

    assert tuple(store.component_key for store in collector.stores) == ('mine', 'plant')
    assert tuple(store.destination_key for store in collector.system_stores) == (
        'global_indicators',
        'time_status',
    )
    assert all(store.is_empty for store in collector.stores)
    assert all(store.is_empty for store in collector.system_stores)


def test_latest_populates_component_and_system_destinations_independently() -> None:
    client = CosmosClientStub()
    _put_latest(client, _latest())
    collector = _collector(client)

    result = collector.refresh_latest()

    assert result.status is KpiCollectorRefreshStatus.UPDATED
    mine = _store(collector, 'mine')
    plant = _store(collector, 'plant')
    global_indicators = _system_store(collector, 'global_indicators')
    time_status = _system_store(collector, 'time_status')
    assert isinstance(mine.payload, ComponentKpiData)
    assert mine.payload.latest is not None
    assert tuple(mine.payload.latest.values) == ('mine_rate',)
    assert plant.is_empty
    assert global_indicators.payload.latest is not None
    assert tuple(global_indicators.payload.latest.values) == ('system_kpi',)
    assert time_status.is_empty


def test_timeseries_populates_component_and_system_destinations() -> None:
    client = CosmosClientStub()
    _put_latest(client, _latest())
    _put_timeseries(client, _timeseries())
    collector = _collector(client)

    collector.refresh_latest()
    result = collector.refresh_timeseries()

    assert result.status is KpiCollectorRefreshStatus.UPDATED
    mine = _store(collector, 'mine')
    plant = _store(collector, 'plant')
    time_status = _system_store(collector, 'time_status')
    assert mine.payload.latest is not None
    assert mine.payload.timeseries is not None
    assert tuple(mine.payload.timeseries.series) == ('mine_rate',)
    assert plant.payload.latest is None
    assert plant.payload.timeseries is not None
    assert tuple(plant.payload.timeseries.series) == ('plant_rate',)
    assert time_status.payload.latest is None
    assert tuple(time_status.payload.timeseries.series) == ('system_series',)


def test_unknown_latest_destination_fails_before_state_mutation() -> None:
    client = CosmosClientStub()
    document = _latest()
    document['destinations']['typo_destination'] = document['destinations'].pop('global_indicators')
    _put_latest(client, document)
    collector = _collector(client)

    with pytest.raises(KpiCollectorContractError, match="unknown destination 'typo_destination'"):
        collector.refresh_latest()

    assert all(store.is_empty for store in collector.stores)
    assert all(store.is_empty for store in collector.system_stores)


def test_unknown_timeseries_destination_fails_before_state_mutation() -> None:
    client = CosmosClientStub()
    document = _timeseries()
    document['destinations']['typo_destination'] = document['destinations'].pop('time_status')
    _put_timeseries(client, document)
    collector = _collector(client)

    with pytest.raises(KpiCollectorContractError, match="unknown destination 'typo_destination'"):
        collector.refresh_timeseries()

    assert all(store.is_empty for store in collector.stores)
    assert all(store.is_empty for store in collector.system_stores)


def test_latest_rejects_value_kind_outside_delivery_contract() -> None:
    client = CosmosClientStub()
    document = _latest()
    document['destinations']['mine']['mine_rate']['value_kind'] = 'integer'
    _put_latest(client, document)
    collector = _collector(client)

    with pytest.raises(KpiCollectorContractError, match='value_kind is invalid'):
        collector.refresh_latest()


def test_new_latest_configuration_is_published_immediately_and_drops_old_timeseries() -> None:
    client = CosmosClientStub()
    _put_latest(client, _latest())
    _put_timeseries(client, _timeseries())
    collector = _collector(client)
    collector.refresh_latest()
    collector.refresh_timeseries()

    _put_latest(
        client,
        _latest(
            revision='latest-r2',
            configuration_revision='kpis-r2',
            watermark=datetime(2026, 9, 20, 22, 2, tzinfo=UTC),
        ),
    )
    result = collector.refresh_latest()

    assert result.status is KpiCollectorRefreshStatus.UPDATED
    mine = _store(collector, 'mine')
    assert mine.payload.latest.manifest['configuration_revision'] == 'kpis-r2'
    assert mine.payload.timeseries is None
    assert _store(collector, 'plant').is_empty
    assert _system_store(collector, 'time_status').is_empty


def test_incompatible_timeseries_never_displaces_current_latest() -> None:
    client = CosmosClientStub()
    _put_latest(client, _latest(configuration_revision='kpis-r2'))
    _put_timeseries(client, _timeseries(configuration_revision='kpis-r1'))
    collector = _collector(client)
    collector.refresh_latest()

    result = collector.refresh_timeseries()

    assert result.status is KpiCollectorRefreshStatus.INCOMPATIBLE
    mine = _store(collector, 'mine')
    assert mine.payload.latest is not None
    assert mine.payload.timeseries is None
    assert _store(collector, 'plant').is_empty


def test_delivery_for_other_tool_projection_is_rejected_without_mutating_stores() -> None:
    client = CosmosClientStub()
    _put_latest(client, _latest(tool_revision='tool-r2'))
    collector = _collector(client)

    result = collector.refresh_latest()

    assert result.status is KpiCollectorRefreshStatus.INCOMPATIBLE
    assert all(store.is_empty for store in collector.stores)
    assert all(store.is_empty for store in collector.system_stores)


def test_missing_document_preserves_last_good_store_state() -> None:
    client = CosmosClientStub()
    _put_latest(client, _latest())
    collector = _collector(client)
    collector.refresh_latest()
    before = collector.snapshot
    client.documents.clear()

    result = collector.refresh_latest()

    assert result.status is KpiCollectorRefreshStatus.MISSING
    assert collector.snapshot == before


def test_stale_latest_watermark_is_rejected_without_regression() -> None:
    client = CosmosClientStub()
    _put_latest(
        client,
        _latest(
            revision='latest-r2',
            watermark=datetime(2026, 9, 20, 22, 2, tzinfo=UTC),
        ),
    )
    collector = _collector(client)
    collector.refresh_latest()
    before = collector.snapshot
    _put_latest(
        client,
        _latest(
            revision='latest-r1',
            watermark=datetime(2026, 9, 20, 22, 0, tzinfo=UTC),
        ),
    )

    result = collector.refresh_latest()

    assert result.status is KpiCollectorRefreshStatus.STALE
    assert collector.snapshot == before


def test_invalid_timeseries_contract_fails_before_state_mutation() -> None:
    client = CosmosClientStub()
    _put_latest(client, _latest())
    _put_timeseries(client, _timeseries())
    collector = _collector(client)
    collector.refresh_latest()
    before = collector.snapshot
    document = _timeseries(revision='timeseries-invalid')
    document['series']['mine_rate']['values'] = [1.0]
    _put_timeseries(client, document)

    with pytest.raises(KpiCollectorContractError, match='values length is invalid'):
        collector.refresh_timeseries()

    assert collector.snapshot == before


def test_timeseries_can_advance_while_latest_remains_unchanged() -> None:
    client = CosmosClientStub()
    _put_latest(client, _latest())
    _put_timeseries(client, _timeseries())
    collector = _collector(client)
    collector.refresh_latest()
    collector.refresh_timeseries()

    _put_timeseries(
        client,
        _timeseries(
            revision='timeseries-r2',
            end=datetime(2026, 9, 20, 22, 2, tzinfo=UTC),
        ),
    )
    result = collector.refresh_timeseries()

    assert result.status is KpiCollectorRefreshStatus.UPDATED
    mine = _store(collector, 'mine')
    assert mine.payload.latest.manifest['revision'] == 'latest-r1'
    assert mine.payload.timeseries.manifest['revision'] == 'timeseries-r2'
    assert _system_store(collector, 'time_status').payload.timeseries.manifest['revision'] == (
        'timeseries-r2'
    )


def test_published_payloads_are_deeply_read_only() -> None:
    client = CosmosClientStub()
    _put_latest(client, _latest())
    _put_timeseries(client, _timeseries())
    collector = _collector(client)
    collector.refresh_latest()
    collector.refresh_timeseries()
    component_payload = _store(collector, 'mine').payload
    system_payload = _system_store(collector, 'global_indicators').payload

    with pytest.raises(TypeError):
        component_payload.latest.manifest['revision'] = 'mutated'
    with pytest.raises(TypeError):
        component_payload.latest.values['mine_rate']['value'] = 0.0
    with pytest.raises(TypeError):
        component_payload.timeseries.series['mine_rate']['hours'] = 2
    with pytest.raises(TypeError):
        system_payload.latest.values['system_kpi']['value'] = 0.0
    assert isinstance(component_payload.timeseries.series['mine_rate']['values'], tuple)


def test_latest_can_advance_while_compatible_timeseries_remains_cached() -> None:
    client = CosmosClientStub()
    _put_latest(client, _latest())
    _put_timeseries(client, _timeseries())
    collector = _collector(client)
    collector.refresh_latest()
    collector.refresh_timeseries()

    _put_latest(
        client,
        _latest(
            revision='latest-r2',
            watermark=datetime(2026, 9, 20, 22, 1, tzinfo=UTC),
        ),
    )
    result = collector.refresh_latest()

    assert result.status is KpiCollectorRefreshStatus.UPDATED
    mine = _store(collector, 'mine')
    assert mine.payload.latest.manifest['revision'] == 'latest-r2'
    assert mine.payload.timeseries.manifest['revision'] == 'timeseries-r1'
    assert _system_store(collector, 'time_status').payload.timeseries.manifest['revision'] == (
        'timeseries-r1'
    )
