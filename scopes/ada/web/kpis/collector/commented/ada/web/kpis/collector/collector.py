# El collector mantiene el último estado válido de Latest y Timeseries y reconstruye stores
# lógicos por componente usando exclusivamente la identidad definida por ToolStructure.

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from types import MappingProxyType
from typing import Any

from ada.web.components import (
    ComponentDelivery,
    ComponentStoreSnapshot,
    build_empty_component_stores,
    collect_component_deliveries,
)
from ada.web.kpis.collector.contracts import (
    KPI_DELIVERY_PARTITION_ID,
    KPI_LATEST_DELIVERY_DOCUMENT_TYPE,
    KPI_LATEST_DELIVERY_ITEM_ID,
    KPI_LATEST_DELIVERY_SCHEMA_VERSION,
    KPI_TIMESERIES_DELIVERY_DOCUMENT_TYPE,
    KPI_TIMESERIES_DELIVERY_ITEM_ID,
    KPI_TIMESERIES_DELIVERY_SCHEMA_VERSION,
    KPI_TIMESERIES_STEP_SECONDS,
)
from ada.web.kpis.collector.models import (
    ComponentKpiData,
    ComponentLatestKpiData,
    ComponentTimeseriesKpiData,
    KpiCollectorContractError,
    KpiCollectorRefreshResult,
    KpiCollectorRefreshStatus,
    KpiCollectorSnapshot,
    KpiDeliveryReader,
)
from ada.web.tools.structure import ToolStructure

_LATEST_DOCUMENT_FIELDS = frozenset(
    {'id', 'partition_id', 'document_type', 'manifest', 'destinations'}
)
_LATEST_MANIFEST_FIELDS = frozenset(
    {
        'schema_version',
        'revision',
        'configuration_revision',
        'tool_projection_revision',
        'watermark_utc',
        'published_at_utc',
    }
)
_LATEST_VALUE_FIELDS = frozenset({'status', 'value_kind', 'value'})
_TIMESERIES_DOCUMENT_FIELDS = frozenset(
    {
        'id',
        'partition_id',
        'document_type',
        'manifest',
        'end_utc',
        'step_seconds',
        'destinations',
        'series',
    }
)
_TIMESERIES_MANIFEST_FIELDS = frozenset(
    {
        'schema_version',
        'revision',
        'configuration_revision',
        'tool_projection_revision',
        'historian_revision',
        'published_at_utc',
    }
)
_TIMESERIES_SERIES_FIELDS = frozenset({'hours', 'start_utc', 'end_utc', 'value_type', 'values'})
_VALUE_TYPES = frozenset({'text', 'integer', 'float', 'boolean'})


@dataclass(frozen=True, slots=True)
class _LatestDelivery:
    revision: str
    configuration_revision: str
    tool_projection_revision: str | None
    watermark_utc: datetime
    manifest: dict[str, object]
    destinations: dict[str, dict[str, dict[str, object]]]

    @property
    def compatibility_key(self) -> tuple[str, str | None]:
        return self.configuration_revision, self.tool_projection_revision


@dataclass(frozen=True, slots=True)
class _TimeseriesDelivery:
    revision: str
    configuration_revision: str
    tool_projection_revision: str | None
    end_utc: datetime
    end_utc_text: str
    step_seconds: int
    manifest: dict[str, object]
    destinations: dict[str, tuple[str, ...]]
    series: dict[str, dict[str, object]]

    @property
    def compatibility_key(self) -> tuple[str, str | None]:
        return self.configuration_revision, self.tool_projection_revision


class AdaKpiCollector:
    def __init__(
        self,
        *,
        structure: ToolStructure,
        tool_projection_revision: str,
        reader: KpiDeliveryReader,
    ) -> None:
        if not isinstance(structure, ToolStructure):
            raise TypeError('structure must be ToolStructure')
        if not callable(getattr(reader, 'read_latest', None)):
            raise TypeError('reader must provide a callable read_latest method')
        if not callable(getattr(reader, 'read_timeseries', None)):
            raise TypeError('reader must provide a callable read_timeseries method')
        self._structure = structure
        self._tool_projection_revision = _required_text(
            tool_projection_revision,
            'tool_projection_revision',
        )
        self._reader = reader
        self._latest: _LatestDelivery | None = None
        self._timeseries: _TimeseriesDelivery | None = None
        self._stores = build_empty_component_stores(structure)
        self._lock = RLock()

    @property
    def structure(self) -> ToolStructure:
        return self._structure

    @property
    def tool_projection_revision(self) -> str:
        return self._tool_projection_revision

    @property
    def stores(self) -> tuple[ComponentStoreSnapshot, ...]:
        with self._lock:
            return self._stores

    @property
    def snapshot(self) -> KpiCollectorSnapshot:
        with self._lock:
            return KpiCollectorSnapshot(
                stores=self._stores,
                latest_revision=None if self._latest is None else self._latest.revision,
                latest_watermark_utc=(
                    None if self._latest is None else self._latest.manifest['watermark_utc']
                ),
                latest_configuration_revision=(
                    None if self._latest is None else self._latest.configuration_revision
                ),
                timeseries_revision=(
                    None if self._timeseries is None else self._timeseries.revision
                ),
                timeseries_end_utc=(
                    None if self._timeseries is None else self._timeseries.end_utc_text
                ),
                timeseries_configuration_revision=(
                    None if self._timeseries is None else self._timeseries.configuration_revision
                ),
            )

    def refresh_latest(self) -> KpiCollectorRefreshResult:
        document = self._reader.read_latest()
        if document is None:
            return KpiCollectorRefreshResult(KpiCollectorRefreshStatus.MISSING)
        candidate = _parse_latest_delivery(document)

        with self._lock:
            if candidate.tool_projection_revision != self._tool_projection_revision:
                return KpiCollectorRefreshResult(
                    KpiCollectorRefreshStatus.INCOMPATIBLE,
                    candidate.revision,
                )
            current = self._latest
            if current is not None and candidate.watermark_utc < current.watermark_utc:
                return KpiCollectorRefreshResult(
                    KpiCollectorRefreshStatus.STALE,
                    candidate.revision,
                )
            if current is not None and candidate.revision == current.revision:
                return KpiCollectorRefreshResult(
                    KpiCollectorRefreshStatus.UNCHANGED,
                    candidate.revision,
                )

            self._latest = candidate
            if (
                self._timeseries is not None
                and self._timeseries.compatibility_key != candidate.compatibility_key
            ):
                self._timeseries = None
            self._rebuild_stores()
            return KpiCollectorRefreshResult(
                KpiCollectorRefreshStatus.UPDATED,
                candidate.revision,
            )

    def refresh_timeseries(self) -> KpiCollectorRefreshResult:
        document = self._reader.read_timeseries()
        if document is None:
            return KpiCollectorRefreshResult(KpiCollectorRefreshStatus.MISSING)
        candidate = _parse_timeseries_delivery(document)

        with self._lock:
            if candidate.tool_projection_revision != self._tool_projection_revision:
                return KpiCollectorRefreshResult(
                    KpiCollectorRefreshStatus.INCOMPATIBLE,
                    candidate.revision,
                )
            current = self._timeseries
            if current is not None and candidate.end_utc < current.end_utc:
                return KpiCollectorRefreshResult(
                    KpiCollectorRefreshStatus.STALE,
                    candidate.revision,
                )
            if self._latest is not None and (
                candidate.compatibility_key != self._latest.compatibility_key
            ):
                return KpiCollectorRefreshResult(
                    KpiCollectorRefreshStatus.INCOMPATIBLE,
                    candidate.revision,
                )
            if current is not None and candidate.revision == current.revision:
                return KpiCollectorRefreshResult(
                    KpiCollectorRefreshStatus.UNCHANGED,
                    candidate.revision,
                )

            self._timeseries = candidate
            self._rebuild_stores()
            return KpiCollectorRefreshResult(
                KpiCollectorRefreshStatus.UPDATED,
                candidate.revision,
            )

    def _rebuild_stores(self) -> None:
        stores = build_empty_component_stores(self._structure)
        deliveries: list[ComponentDelivery] = []
        for component in self._structure.components:
            latest = _component_latest(self._latest, component.key)
            timeseries = _component_timeseries(self._timeseries, component.key)
            if latest is None and timeseries is None:
                continue
            deliveries.append(
                ComponentDelivery(
                    tool_key=self._structure.tool_key,
                    component_key=component.key,
                    payload=ComponentKpiData(
                        latest=latest,
                        timeseries=timeseries,
                    ),
                )
            )
        self._stores = collect_component_deliveries(stores, deliveries)


def _component_latest(
    delivery: _LatestDelivery | None,
    component_key: str,
) -> ComponentLatestKpiData | None:
    if delivery is None:
        return None
    values = delivery.destinations.get(component_key)
    if values is None:
        return None
    return ComponentLatestKpiData(
        manifest=_freeze_mapping(delivery.manifest),
        values=MappingProxyType({key: _freeze_mapping(value) for key, value in values.items()}),
    )


def _component_timeseries(
    delivery: _TimeseriesDelivery | None,
    component_key: str,
) -> ComponentTimeseriesKpiData | None:
    if delivery is None:
        return None
    keys = delivery.destinations.get(component_key)
    if keys is None:
        return None
    return ComponentTimeseriesKpiData(
        manifest=_freeze_mapping(delivery.manifest),
        end_utc=delivery.end_utc_text,
        step_seconds=delivery.step_seconds,
        series=MappingProxyType({key: _freeze_mapping(delivery.series[key]) for key in keys}),
    )


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value


def _parse_latest_delivery(document: Mapping[str, Any]) -> _LatestDelivery:
    value = _document(document, _LATEST_DOCUMENT_FIELDS, 'KPI latest delivery')
    _require_identity(
        value,
        item_id=KPI_LATEST_DELIVERY_ITEM_ID,
        document_type=KPI_LATEST_DELIVERY_DOCUMENT_TYPE,
        label='KPI latest delivery',
    )
    manifest = _mapping(value['manifest'], 'KPI latest delivery manifest')
    _require_exact_fields(
        manifest,
        _LATEST_MANIFEST_FIELDS,
        'KPI latest delivery manifest',
    )
    if manifest['schema_version'] != KPI_LATEST_DELIVERY_SCHEMA_VERSION:
        raise KpiCollectorContractError('KPI latest delivery schema_version is invalid')
    revision = _required_text(manifest['revision'], 'latest manifest revision')
    configuration_revision = _required_text(
        manifest['configuration_revision'],
        'latest manifest configuration_revision',
    )
    tool_projection_revision = _optional_text(
        manifest['tool_projection_revision'],
        'latest manifest tool_projection_revision',
    )
    watermark_utc = _utc_datetime(manifest['watermark_utc'], 'latest manifest watermark_utc')
    _utc_datetime(manifest['published_at_utc'], 'latest manifest published_at_utc')

    destinations_value = _mapping(value['destinations'], 'KPI latest delivery destinations')
    destinations: dict[str, dict[str, dict[str, object]]] = {}
    for destination_key, raw_values in destinations_value.items():
        destination = _required_text(destination_key, 'latest destination key')
        values = _mapping(raw_values, f'latest destination {destination!r}')
        projected: dict[str, dict[str, object]] = {}
        for kpi_key, raw_value in values.items():
            key = _required_text(kpi_key, 'latest KPI key')
            payload = _mapping(raw_value, f'latest KPI {key!r}')
            _require_exact_fields(payload, _LATEST_VALUE_FIELDS, f'latest KPI {key!r}')
            _validate_latest_value(payload, key)
            projected[key] = dict(payload)
        destinations[destination] = projected

    return _LatestDelivery(
        revision=revision,
        configuration_revision=configuration_revision,
        tool_projection_revision=tool_projection_revision,
        watermark_utc=watermark_utc,
        manifest=dict(manifest),
        destinations=destinations,
    )


def _parse_timeseries_delivery(document: Mapping[str, Any]) -> _TimeseriesDelivery:
    value = _document(document, _TIMESERIES_DOCUMENT_FIELDS, 'KPI timeseries delivery')
    _require_identity(
        value,
        item_id=KPI_TIMESERIES_DELIVERY_ITEM_ID,
        document_type=KPI_TIMESERIES_DELIVERY_DOCUMENT_TYPE,
        label='KPI timeseries delivery',
    )
    manifest = _mapping(value['manifest'], 'KPI timeseries delivery manifest')
    _require_exact_fields(
        manifest,
        _TIMESERIES_MANIFEST_FIELDS,
        'KPI timeseries delivery manifest',
    )
    if manifest['schema_version'] != KPI_TIMESERIES_DELIVERY_SCHEMA_VERSION:
        raise KpiCollectorContractError('KPI timeseries delivery schema_version is invalid')
    revision = _required_text(manifest['revision'], 'timeseries manifest revision')
    configuration_revision = _required_text(
        manifest['configuration_revision'],
        'timeseries manifest configuration_revision',
    )
    tool_projection_revision = _optional_text(
        manifest['tool_projection_revision'],
        'timeseries manifest tool_projection_revision',
    )
    _required_text(manifest['historian_revision'], 'timeseries manifest historian_revision')
    _utc_datetime(manifest['published_at_utc'], 'timeseries manifest published_at_utc')

    end_utc_text = _required_text(value['end_utc'], 'timeseries end_utc')
    end_utc = _utc_datetime(end_utc_text, 'timeseries end_utc')
    step_seconds = value['step_seconds']
    if step_seconds != KPI_TIMESERIES_STEP_SECONDS:
        raise KpiCollectorContractError(
            f'KPI timeseries step_seconds must be {KPI_TIMESERIES_STEP_SECONDS}'
        )

    raw_series = _mapping(value['series'], 'KPI timeseries series')
    series: dict[str, dict[str, object]] = {}
    for kpi_key, raw_value in raw_series.items():
        key = _required_text(kpi_key, 'timeseries KPI key')
        payload = _mapping(raw_value, f'timeseries KPI {key!r}')
        _require_exact_fields(payload, _TIMESERIES_SERIES_FIELDS, f'timeseries KPI {key!r}')
        _validate_timeseries_series(
            payload,
            key=key,
            root_end_utc=end_utc,
            step_seconds=step_seconds,
        )
        series[key] = dict(payload)

    raw_destinations = _mapping(value['destinations'], 'KPI timeseries destinations')
    destinations: dict[str, tuple[str, ...]] = {}
    for destination_key, raw_keys in raw_destinations.items():
        destination = _required_text(destination_key, 'timeseries destination key')
        if not isinstance(raw_keys, list):
            raise KpiCollectorContractError(
                f'KPI timeseries destination {destination!r} must be an array'
            )
        keys = tuple(_required_text(item, 'timeseries destination KPI key') for item in raw_keys)
        if len(keys) != len(set(keys)):
            raise KpiCollectorContractError(
                f'KPI timeseries destination {destination!r} contains duplicate KPI keys'
            )
        missing = next((key for key in keys if key not in series), None)
        if missing is not None:
            raise KpiCollectorContractError(
                f'KPI timeseries destination {destination!r} references missing series {missing!r}'
            )
        destinations[destination] = keys

    return _TimeseriesDelivery(
        revision=revision,
        configuration_revision=configuration_revision,
        tool_projection_revision=tool_projection_revision,
        end_utc=end_utc,
        end_utc_text=end_utc_text,
        step_seconds=step_seconds,
        manifest=dict(manifest),
        destinations=destinations,
        series=series,
    )


def _validate_latest_value(value: Mapping[str, Any], key: str) -> None:
    status = value['status']
    value_kind = value['value_kind']
    payload = value['value']
    if status not in {'ok', 'missing', 'error'}:
        raise KpiCollectorContractError(f'KPI latest value {key!r} status is invalid')
    if value_kind is not None:
        _required_text(value_kind, f'KPI latest value {key!r} value_kind')
    if status == 'ok':
        if value_kind is None or payload is None:
            raise KpiCollectorContractError(
                f'KPI latest value {key!r} requires value_kind and value when status is ok'
            )
        return
    if status == 'missing':
        if value_kind is not None or payload is not None:
            raise KpiCollectorContractError(
                f'KPI latest value {key!r} must be empty when status is missing'
            )
        return
    if payload is not None:
        raise KpiCollectorContractError(
            f'KPI latest value {key!r} must not contain value when status is error'
        )


def _validate_timeseries_series(
    value: Mapping[str, Any],
    *,
    key: str,
    root_end_utc: datetime,
    step_seconds: int,
) -> None:
    hours = value['hours']
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 24:
        raise KpiCollectorContractError(
            f'KPI timeseries series {key!r} hours must be between 1 and 24'
        )
    start_utc = _utc_datetime(value['start_utc'], f'timeseries series {key!r} start_utc')
    end_utc = _utc_datetime(value['end_utc'], f'timeseries series {key!r} end_utc')
    if end_utc != root_end_utc:
        raise KpiCollectorContractError(
            f'KPI timeseries series {key!r} end_utc must match delivery end_utc'
        )
    if start_utc != end_utc - timedelta(hours=hours):
        raise KpiCollectorContractError(
            f'KPI timeseries series {key!r} start_utc is inconsistent with hours'
        )
    value_type = value['value_type']
    if value_type is not None and value_type not in _VALUE_TYPES:
        raise KpiCollectorContractError(f'KPI timeseries series {key!r} value_type is invalid')
    values = value['values']
    if not isinstance(values, list):
        raise KpiCollectorContractError(f'KPI timeseries series {key!r} values must be an array')
    expected_count = hours * 3600 // step_seconds
    if len(values) != expected_count:
        raise KpiCollectorContractError(f'KPI timeseries series {key!r} values length is invalid')
    for item in values:
        _validate_series_scalar(item, value_type=value_type, key=key)


def _validate_series_scalar(value: object, *, value_type: object, key: str) -> None:
    if value is None:
        return
    if value_type is None:
        raise KpiCollectorContractError(
            f'KPI timeseries series {key!r} requires value_type when values are present'
        )
    if value_type == 'text' and isinstance(value, str):
        return
    if value_type == 'boolean' and isinstance(value, bool):
        return
    if value_type == 'integer' and isinstance(value, int) and not isinstance(value, bool):
        return
    if value_type == 'float' and isinstance(value, float):
        return
    raise KpiCollectorContractError(
        f'KPI timeseries series {key!r} contains a value incompatible with value_type'
    )


def _document(
    value: object,
    expected_fields: frozenset[str],
    label: str,
) -> Mapping[str, Any]:
    document = _mapping(value, label)
    _require_exact_fields(document, expected_fields, label)
    return document


def _require_identity(
    document: Mapping[str, Any],
    *,
    item_id: str,
    document_type: str,
    label: str,
) -> None:
    if document['id'] != item_id:
        raise KpiCollectorContractError(f'{label} id is invalid')
    if document['partition_id'] != KPI_DELIVERY_PARTITION_ID:
        raise KpiCollectorContractError(f'{label} partition_id is invalid')
    if document['document_type'] != document_type:
        raise KpiCollectorContractError(f'{label} document_type is invalid')


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KpiCollectorContractError(f'{label} must be an object')
    return value


def _require_exact_fields(
    value: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    if set(value) != expected:
        raise KpiCollectorContractError(f'{label} contains unexpected or missing fields')


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KpiCollectorContractError(f'{field_name} must be a non-empty string')
    if value != value.strip():
        raise KpiCollectorContractError(f'{field_name} must not contain surrounding whitespace')
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _utc_datetime(value: object, field_name: str) -> datetime:
    text = _required_text(value, field_name)
    candidate = f'{text[:-1]}+00:00' if text.endswith('Z') else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise KpiCollectorContractError(f'{field_name} must be an ISO-8601 timestamp') from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KpiCollectorContractError(f'{field_name} must be timezone-aware')
    return parsed.astimezone(UTC)
