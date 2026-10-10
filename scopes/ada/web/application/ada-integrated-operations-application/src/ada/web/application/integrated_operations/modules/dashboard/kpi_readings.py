from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ada.web.kpis.collector import (
    DecodedKpiLatestValue,
    KpiLatestValueState,
    decode_kpi_latest_value,
)
from ada.web.ui.display_status import DisplayStatus, DisplayValue


@dataclass(frozen=True, slots=True)
class DashboardLatestReadings:
    values: Mapping[str, object] | None
    source_status: DisplayStatus

    def __post_init__(self) -> None:
        if not isinstance(self.source_status, DisplayStatus):
            raise TypeError('source_status must be DisplayStatus')
        if self.source_status is DisplayStatus.OK:
            if not isinstance(self.values, Mapping):
                raise ValueError('OK source requires a values mapping')
        elif self.values is not None:
            raise ValueError('Degraded source cannot expose values')

    def scalar(self, key: str, *, allow_bool: bool = False) -> DisplayValue:
        decoded = self._decode(key)
        if decoded is None:
            return DisplayValue(self.source_status)
        if decoded.state is not KpiLatestValueState.OK:
            return _degraded(decoded.state)
        if decoded.value_kind != 'value':
            return DisplayValue.invalid()
        value = decoded.value
        if not isinstance(value, str | int | float) or (isinstance(value, bool) and not allow_bool):
            return DisplayValue.invalid()
        return DisplayValue.ok(value)

    def text(self, key: str) -> DisplayValue:
        result = self.scalar(key)
        if result.status is not DisplayStatus.OK:
            return result
        value = str(result.value).strip()
        return DisplayValue.ok(value) if value else DisplayValue.invalid()

    def json(self, key: str) -> DisplayValue:
        decoded = self._decode(key)
        if decoded is None:
            return DisplayValue(self.source_status)
        if decoded.state is not KpiLatestValueState.OK:
            return _degraded(decoded.state)
        if decoded.value_kind != 'json' or not isinstance(decoded.value, list | dict):
            return DisplayValue.invalid()
        return DisplayValue.ok(decoded.value)

    def _decode(self, key: str) -> DecodedKpiLatestValue | None:
        if not isinstance(key, str) or not key or key != key.strip():
            raise ValueError('KPI key must be a non-empty trimmed string')
        if self.values is None:
            return None
        return decode_kpi_latest_value(self.values.get(key), present=key in self.values)


def read_component_latest(store_data: object) -> DashboardLatestReadings:
    return _read_latest(store_data)


def read_system_latest(
    store_data: object, *, tool_key: str, destination_key: str
) -> DashboardLatestReadings:
    for name, key in (('tool_key', tool_key), ('destination_key', destination_key)):
        if not isinstance(key, str) or not key or key != key.strip():
            raise ValueError(f'{name} must be a non-empty trimmed string')
    if not isinstance(store_data, Mapping):
        return DashboardLatestReadings(None, DisplayStatus.INVALID)
    if (
        store_data.get('tool_key') != tool_key
        or store_data.get('destination_key') != destination_key
    ):
        return DashboardLatestReadings(None, DisplayStatus.INVALID)
    return _read_latest(store_data)


def _read_latest(store_data: object) -> DashboardLatestReadings:
    if not isinstance(store_data, Mapping):
        return DashboardLatestReadings(None, DisplayStatus.INVALID)
    latest = store_data.get('latest')
    if latest is None:
        return DashboardLatestReadings(None, DisplayStatus.NOT_MAPPED)
    if not isinstance(latest, Mapping):
        return DashboardLatestReadings(None, DisplayStatus.INVALID)
    values = latest.get('values')
    if not isinstance(values, Mapping):
        return DashboardLatestReadings(None, DisplayStatus.INVALID)
    return DashboardLatestReadings(values, DisplayStatus.OK)


def _degraded(state: KpiLatestValueState) -> DisplayValue:
    if state is KpiLatestValueState.NOT_MAPPED:
        return DisplayValue.not_mapped()
    if state is KpiLatestValueState.MISSING:
        return DisplayValue.empty()
    if state is KpiLatestValueState.ERROR:
        return DisplayValue.error()
    return DisplayValue.invalid()
