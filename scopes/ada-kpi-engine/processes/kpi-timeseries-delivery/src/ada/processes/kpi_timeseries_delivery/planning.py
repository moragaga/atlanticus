from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ada.kpis.delivery import (
    KpiDeliveryBinding,
    KpiDeliveryConfiguration,
    KpiDeliveryValidationError,
    canonical_revision,
)
from ada.kpis.materialization import (
    KpiMaterializationContractError,
    KpiMaterializationStoreError,
    LocalKpiRegistryStore,
    require_tool_key,
)
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryConfigurationError,
    KpiTimeseriesDeliveryReadinessPending,
)


@dataclass(frozen=True, slots=True)
class FrozenKpiTimeseriesConfiguration:
    tool_key: str
    registry_revision: str
    registry_digest: str
    configuration: KpiDeliveryConfiguration


@dataclass(frozen=True, slots=True)
class KpiTimeseriesReadPlan:
    required_columns: tuple[str, ...]
    max_window_hours: int

    def __post_init__(self) -> None:
        if not isinstance(self.required_columns, tuple):
            raise TypeError('required_columns must be tuple')
        if any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in self.required_columns
        ):
            raise ValueError('required_columns must contain non-empty trimmed strings')
        if tuple(sorted(set(self.required_columns))) != self.required_columns:
            raise ValueError('required_columns must be sorted and unique')
        if isinstance(self.max_window_hours, bool) or not isinstance(self.max_window_hours, int):
            raise TypeError('max_window_hours must be int')
        if not 0 <= self.max_window_hours <= 24:
            raise ValueError('max_window_hours must be between 0 and 24')


def load_frozen_timeseries_configurations(
    *,
    store: LocalKpiRegistryStore,
    expected_tool_keys: Iterable[str],
) -> Mapping[str, FrozenKpiTimeseriesConfiguration]:
    if not isinstance(store, LocalKpiRegistryStore):
        raise TypeError('store must be LocalKpiRegistryStore')
    expected = tuple(sorted({require_tool_key(value) for value in expected_tool_keys}))
    if not expected:
        raise KpiTimeseriesDeliveryConfigurationError(
            'Timeseries delivery requires at least one configured tool'
        )
    try:
        actual = store.tool_keys()
    except KpiMaterializationStoreError as error:
        raise KpiTimeseriesDeliveryConfigurationError(
            'Could not inspect materialized KPI Registries'
        ) from error
    if actual != expected:
        missing = sorted(set(expected).difference(actual))
        unexpected = sorted(set(actual).difference(expected))
        details: list[str] = []
        if missing:
            details.append(f'missing={",".join(missing)}')
        if unexpected:
            details.append(f'unexpected={",".join(unexpected)}')
        suffix = f' ({"; ".join(details)})' if details else ''
        raise KpiTimeseriesDeliveryReadinessPending(
            f'Materialized KPI Registry set is not ready{suffix}'
        )

    frozen: dict[str, FrozenKpiTimeseriesConfiguration] = {}
    for tool_key in expected:
        try:
            document = store.read(tool_key)
        except (KpiMaterializationContractError, KpiMaterializationStoreError) as error:
            raise KpiTimeseriesDeliveryConfigurationError(
                f'Materialized KPI Registry is invalid for {tool_key}'
            ) from error
        if document is None:
            raise KpiTimeseriesDeliveryReadinessPending(
                f'Materialized KPI Registry is not ready for {tool_key}'
            )
        try:
            configuration = _configuration_from_materialized(document)
            digest = canonical_revision(document)
        except (KpiDeliveryValidationError, TypeError, ValueError) as error:
            raise KpiTimeseriesDeliveryConfigurationError(
                f'Materialized KPI Registry is invalid for {tool_key}'
            ) from error
        frozen[tool_key] = FrozenKpiTimeseriesConfiguration(
            tool_key=tool_key,
            registry_revision=configuration.revision,
            registry_digest=digest,
            configuration=configuration,
        )
    return MappingProxyType(frozen)


def build_timeseries_read_plan(
    configurations: Mapping[str, FrozenKpiTimeseriesConfiguration],
) -> KpiTimeseriesReadPlan:
    if not isinstance(configurations, Mapping) or not configurations:
        raise ValueError('configurations must contain at least one tool')
    required: set[str] = set()
    max_window_hours = 0
    for tool_key, frozen in configurations.items():
        if not isinstance(tool_key, str) or require_tool_key(tool_key) != tool_key:
            raise ValueError('configuration mapping contains an invalid tool key')
        if not isinstance(frozen, FrozenKpiTimeseriesConfiguration):
            raise TypeError('configurations must contain FrozenKpiTimeseriesConfiguration values')
        if frozen.tool_key != tool_key:
            raise ValueError('configuration mapping tool key mismatch')
        for binding in frozen.configuration.bindings:
            if not binding.series_enabled:
                continue
            if binding.series_hours is None:
                raise KpiTimeseriesDeliveryConfigurationError(
                    f'series_hours is required for enabled series in {tool_key}'
                )
            required.add(binding.key)
            max_window_hours = max(max_window_hours, binding.series_hours)
    return KpiTimeseriesReadPlan(
        required_columns=tuple(sorted(required)),
        max_window_hours=max_window_hours,
    )


def _configuration_from_materialized(
    document: Mapping[str, Any],
) -> KpiDeliveryConfiguration:
    revision = _required_text(document.get('source_release_id'), 'source_release_id')
    tool_revision = _tool_projection_revision(document.get('dependencies'))
    payload = document.get('payload')
    if not isinstance(payload, Mapping) or set(payload) != {'bindings', 'tool_key'}:
        raise KpiTimeseriesDeliveryConfigurationError('KPI Registry projection payload is invalid')
    if payload['tool_key'] != document.get('tool_key'):
        raise KpiTimeseriesDeliveryConfigurationError(
            'KPI Registry payload tool_key does not match materialized tool_key'
        )
    raw_bindings = payload['bindings']
    if not isinstance(raw_bindings, list):
        raise KpiTimeseriesDeliveryConfigurationError('KPI Registry bindings must be an array')
    bindings = tuple(
        _binding_from_payload(value, index) for index, value in enumerate(raw_bindings)
    )
    return KpiDeliveryConfiguration(
        revision=revision,
        tool_projection_revision=tool_revision,
        bindings=bindings,
    )


def _tool_projection_revision(value: object) -> str:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], Mapping):
        raise KpiTimeseriesDeliveryConfigurationError(
            'KPI Registry projection must contain exactly one dependency'
        )
    return _required_text(
        value[0].get('source_release_id'),
        'dependencies[0].source_release_id',
    )


def _binding_from_payload(value: object, index: int) -> KpiDeliveryBinding:
    if not isinstance(value, Mapping):
        raise KpiTimeseriesDeliveryConfigurationError(
            f'KPI Registry binding {index} must be an object'
        )
    destinations = value.get('destination_keys')
    if not isinstance(destinations, list):
        raise KpiTimeseriesDeliveryConfigurationError(
            f'KPI Registry binding {index} destination_keys must be an array'
        )
    return KpiDeliveryBinding(
        key=_required_text(value.get('kpi_key'), f'bindings[{index}].kpi_key'),
        destination_keys=tuple(destinations),
        latest_enabled=_required_bool(
            value.get('latest_enabled'),
            f'bindings[{index}].latest_enabled',
        ),
        series_enabled=_required_bool(
            value.get('series_enabled'),
            f'bindings[{index}].series_enabled',
        ),
        series_hours=value.get('series_hours'),
    )


def _required_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise KpiTimeseriesDeliveryConfigurationError(f'{field_name} must be boolean')
    return value


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must be non-empty trimmed text'
        )
    return value
