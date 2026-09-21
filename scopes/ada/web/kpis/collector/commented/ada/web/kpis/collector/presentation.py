# Proyección Web del collector. Deriva IDs desde ToolStructure, serializa el cache a JSON y
# reconcilia Latest y Timeseries de forma independiente sin permitir regresiones entre workers.

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from dash import no_update

from ada.web.components import ComponentStoreSnapshot
from ada.web.kpis.collector.models import ComponentKpiData, KpiCollectorSnapshot
from ada.web.tools.structure import ToolStructure

KPI_COMPONENT_STORE_TYPE = 'ada-kpi-component-store'
DEFAULT_KPI_BROWSER_REFRESH_INTERVAL_SECONDS = 10.0
DEFAULT_KPI_COLLECTOR_INTERVAL_ID = 'ada-kpi-collector-refresh'
DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID = 'ada-kpi-collector-browser-revision'


def _validate_interval(value: object, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f'{field_name} must be greater than zero and finite')


def _validate_component_id(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{field_name} has an invalid format')


def _validate_key(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{field_name} has an invalid format')
    return value


class KpiCollectorPresentationSource(Protocol):
    @property
    def structure(self) -> ToolStructure: ...

    @property
    def snapshot(self) -> KpiCollectorSnapshot: ...


@dataclass(frozen=True, slots=True)
class KpiCollectorPresentationSettings:
    refresh_interval_seconds: float = DEFAULT_KPI_BROWSER_REFRESH_INTERVAL_SECONDS
    interval_id: str = DEFAULT_KPI_COLLECTOR_INTERVAL_ID
    revision_store_id: str = DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID

    def __post_init__(self) -> None:
        _validate_interval(self.refresh_interval_seconds, 'refresh_interval_seconds')
        _validate_component_id(self.interval_id, 'interval_id')
        _validate_component_id(self.revision_store_id, 'revision_store_id')
        if self.interval_id == self.revision_store_id:
            raise ValueError('KPI collector interval and revision Store ids must be different')


def component_kpi_store_id(tool_key: str, component_key: str) -> dict[str, str]:
    return {
        'type': KPI_COMPONENT_STORE_TYPE,
        'tool': _validate_key(tool_key, 'tool_key'),
        'component': _validate_key(component_key, 'component_key'),
    }


def project_component_store_data(store: ComponentStoreSnapshot) -> dict[str, object]:
    if not isinstance(store, ComponentStoreSnapshot):
        raise TypeError('store must be ComponentStoreSnapshot')
    latest = None
    timeseries = None
    if store.payload is not None:
        if not isinstance(store.payload, ComponentKpiData):
            raise TypeError('Component Store payload must be ComponentKpiData')
        if store.payload.latest is not None:
            latest = {
                'manifest': _json_value(store.payload.latest.manifest),
                'values': _json_value(store.payload.latest.values),
            }
        if store.payload.timeseries is not None:
            timeseries = {
                'manifest': _json_value(store.payload.timeseries.manifest),
                'end_utc': store.payload.timeseries.end_utc,
                'step_seconds': store.payload.timeseries.step_seconds,
                'series': _json_value(store.payload.timeseries.series),
            }
    return {
        'tool_key': store.tool_key,
        'component_key': store.component_key,
        'latest': latest,
        'timeseries': timeseries,
    }


def resolve_kpi_collector_browser_update(
    collector: KpiCollectorPresentationSource,
    *,
    browser_revision: object,
    browser_component_data: Sequence[object],
) -> tuple[tuple[object, ...], object]:
    structure = collector.structure
    snapshot = collector.snapshot
    if len(browser_component_data) != len(structure.components):
        raise ValueError('browser_component_data must contain one value per Tool component')
    if not snapshot.has_delivery_data:
        return tuple(no_update for _ in structure.components), no_update

    browser_state = _normalize_browser_revision(browser_revision)
    server_state = snapshot.browser_revision
    latest_action = _source_action(
        candidate=server_state['latest'],
        current=browser_state['latest'],
        marker='watermark_utc',
    )
    effective_latest = (
        server_state['latest'] if latest_action == 'update' else browser_state['latest']
    )
    timeseries_action = _source_action(
        candidate=server_state['timeseries'],
        current=browser_state['timeseries'],
        marker='end_utc',
    )
    server_timeseries = _source_mapping(server_state['timeseries'])
    effective_latest_mapping = _source_mapping(effective_latest)
    if server_timeseries is not None and effective_latest_mapping is not None:
        if server_timeseries.get('configuration_revision') != effective_latest_mapping.get(
            'configuration_revision'
        ):
            timeseries_action = 'keep'

    clear_timeseries = _must_clear_browser_timeseries(
        latest_action=latest_action,
        server_latest=server_state['latest'],
        browser_latest=browser_state['latest'],
        server_timeseries=server_state['timeseries'],
    )
    if latest_action == 'keep' and timeseries_action == 'keep' and not clear_timeseries:
        return tuple(no_update for _ in structure.components), no_update

    server_stores = {store.component_key: store for store in snapshot.stores}
    outputs = tuple(
        _merge_component_store(
            candidate=project_component_store_data(server_stores[component.key]),
            current=browser_component_data[index],
            tool_key=structure.tool_key,
            component_key=component.key,
            update_latest=latest_action == 'update',
            update_timeseries=timeseries_action == 'update',
            clear_timeseries=clear_timeseries,
        )
        for index, component in enumerate(structure.components)
    )
    revision = _merge_browser_revision(
        browser_state=browser_state,
        server_state=server_state,
        update_latest=latest_action == 'update',
        update_timeseries=timeseries_action == 'update',
        clear_timeseries=clear_timeseries,
    )
    return outputs, revision


def _must_clear_browser_timeseries(
    *,
    latest_action: str,
    server_latest: object,
    browser_latest: object,
    server_timeseries: object,
) -> bool:
    if latest_action != 'update' or server_timeseries is not None:
        return False
    server_latest_mapping = _source_mapping(server_latest)
    browser_latest_mapping = _source_mapping(browser_latest)
    return (
        server_latest_mapping is not None
        and browser_latest_mapping is not None
        and server_latest_mapping.get('configuration_revision')
        != browser_latest_mapping.get('configuration_revision')
    )


def _merge_component_store(
    *,
    candidate: Mapping[str, object],
    current: object,
    tool_key: str,
    component_key: str,
    update_latest: bool,
    update_timeseries: bool,
    clear_timeseries: bool,
) -> dict[str, object]:
    updated = _normalize_component_store_data(
        current,
        tool_key=tool_key,
        component_key=component_key,
    )
    if update_latest:
        updated['latest'] = candidate['latest']
    if update_timeseries:
        updated['timeseries'] = candidate['timeseries']
    elif clear_timeseries:
        updated['timeseries'] = None
    return updated


def _merge_browser_revision(
    *,
    browser_state: Mapping[str, object | None],
    server_state: Mapping[str, object | None],
    update_latest: bool,
    update_timeseries: bool,
    clear_timeseries: bool,
) -> dict[str, object | None]:
    revision = dict(browser_state)
    if update_latest:
        revision['latest'] = server_state['latest']
    if update_timeseries:
        revision['timeseries'] = server_state['timeseries']
    elif clear_timeseries:
        revision['timeseries'] = None
    return revision


def _normalize_browser_revision(value: object) -> dict[str, object | None]:
    if not isinstance(value, Mapping):
        return {'latest': None, 'timeseries': None}
    return {
        'latest': value.get('latest'),
        'timeseries': value.get('timeseries'),
    }


def _source_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _source_action(*, candidate: object, current: object, marker: str) -> str:
    candidate_mapping = _source_mapping(candidate)
    if candidate_mapping is None:
        return 'keep'
    current_mapping = _source_mapping(current)
    if current_mapping is None:
        return 'update'
    candidate_marker = _parse_timestamp(candidate_mapping.get(marker))
    current_marker = _parse_timestamp(current_mapping.get(marker))
    if candidate_marker is None:
        raise ValueError(f'collector browser marker is invalid: {marker}')
    if current_marker is None:
        return 'update'
    if candidate_marker > current_marker:
        return 'update'
    if candidate_marker < current_marker:
        return 'keep'
    if candidate_mapping.get('revision') != current_mapping.get('revision'):
        return 'update'
    if candidate_mapping.get('configuration_revision') != current_mapping.get(
        'configuration_revision'
    ):
        return 'update'
    return 'keep'


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _normalize_component_store_data(
    value: object,
    *,
    tool_key: str,
    component_key: str,
) -> dict[str, object]:
    if isinstance(value, Mapping):
        if value.get('tool_key') == tool_key and value.get('component_key') == component_key:
            return {
                'tool_key': tool_key,
                'component_key': component_key,
                'latest': value.get('latest'),
                'timeseries': value.get('timeseries'),
            }
    return {
        'tool_key': tool_key,
        'component_key': component_key,
        'latest': None,
        'timeseries': None,
    }


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value
