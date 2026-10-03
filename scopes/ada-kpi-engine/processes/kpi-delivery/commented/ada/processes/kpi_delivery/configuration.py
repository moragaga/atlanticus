# Espejo pedagógico de readiness de KPI Latest Delivery: configuration.py.
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
    LocalKpiRegistryStore,
    require_tool_key,
    validate_materialized_registry,
)
from ada.processes.kpi_delivery.errors import (
    KpiDeliveryConfigurationError,
    KpiDeliveryReadinessPending,
)


@dataclass(frozen=True, slots=True)
# Define una responsabilidad con estado o contrato propio.
class FrozenKpiDeliveryConfiguration:
    tool_key: str
    registry_revision: str
    registry_digest: str
    configuration: KpiDeliveryConfiguration


# Expone una operación manteniendo validación explícita.
def load_frozen_delivery_configurations(
    *,
    store: LocalKpiRegistryStore,
    expected_tool_keys: Iterable[str],
) -> Mapping[str, FrozenKpiDeliveryConfiguration]:
    if not isinstance(store, LocalKpiRegistryStore):
        raise TypeError('store must be LocalKpiRegistryStore')
    expected = tuple(sorted({require_tool_key(value) for value in expected_tool_keys}))
    if not expected:
        raise KpiDeliveryConfigurationError('Delivery requires at least one configured tool')
    actual = store.tool_keys()
    if actual != expected:
        missing = sorted(set(expected).difference(actual))
        unexpected = sorted(set(actual).difference(expected))
        details = []
        if missing:
            details.append(f'missing={",".join(missing)}')
        if unexpected:
            details.append(f'unexpected={",".join(unexpected)}')
        raise KpiDeliveryReadinessPending(
            'Materialized KPI Registry set is not ready'
            + (f' ({"; ".join(details)})' if details else '')
        )
    frozen: dict[str, FrozenKpiDeliveryConfiguration] = {}
    for tool_key in expected:
        document = store.read(tool_key)
        if document is None:
            raise KpiDeliveryReadinessPending(
                f'Materialized KPI Registry is not ready for {tool_key}'
            )
        try:
            validated = validate_materialized_registry(
                document,
                expected_tool_key=tool_key,
            )
            configuration = _configuration_from_materialized(validated)
            digest = canonical_revision(validated)
        except (
            KpiMaterializationContractError,
            KpiDeliveryValidationError,
            TypeError,
            ValueError,
        ) as error:
            raise KpiDeliveryConfigurationError(
                f'Materialized KPI Registry is invalid for {tool_key}'
            ) from error
        frozen[tool_key] = FrozenKpiDeliveryConfiguration(
            tool_key=tool_key,
            registry_revision=configuration.revision,
            registry_digest=digest,
            configuration=configuration,
        )
    return MappingProxyType(frozen)


# Expone una operación manteniendo validación explícita.
def _configuration_from_materialized(
    document: Mapping[str, Any],
) -> KpiDeliveryConfiguration:
    revision = _required_text(document['source_release_id'], 'source_release_id')
    tool_revision = _tool_projection_revision(document['dependencies'])
    payload = document['payload']
    if not isinstance(payload, Mapping) or set(payload) != {'bindings', 'tool_key'}:
        raise KpiDeliveryConfigurationError('KPI Registry projection payload is invalid')
    if payload['tool_key'] != document['tool_key']:
        raise KpiDeliveryConfigurationError(
            'KPI Registry payload tool_key does not match materialized tool_key'
        )
    raw_bindings = payload['bindings']
    if not isinstance(raw_bindings, list):
        raise KpiDeliveryConfigurationError('KPI Registry bindings must be an array')
    bindings = tuple(
        _binding_from_payload(value, index) for index, value in enumerate(raw_bindings)
    )
    return KpiDeliveryConfiguration(
        revision=revision,
        tool_projection_revision=tool_revision,
        bindings=bindings,
    )


# Expone una operación manteniendo validación explícita.
def _tool_projection_revision(value: object) -> str:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], Mapping):
        raise KpiDeliveryConfigurationError(
            'KPI Registry projection must contain exactly one dependency'
        )
    dependency = value[0]
    return _required_text(
        dependency.get('source_release_id'),
        'dependencies[0].source_release_id',
    )


# Expone una operación manteniendo validación explícita.
def _binding_from_payload(value: object, index: int) -> KpiDeliveryBinding:
    if not isinstance(value, Mapping):
        raise KpiDeliveryConfigurationError(f'KPI Registry binding {index} must be an object')
    destinations = value.get('destination_keys')
    if not isinstance(destinations, list):
        raise KpiDeliveryConfigurationError(
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


# Expone una operación manteniendo validación explícita.
def _required_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise KpiDeliveryConfigurationError(f'{field_name} must be boolean')
    return value


# Expone una operación manteniendo validación explícita.
def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KpiDeliveryConfigurationError(f'{field_name} must be a non-empty string')
    if value != value.strip():
        raise KpiDeliveryConfigurationError(
            f'{field_name} must not contain surrounding whitespace'
        )
    return value
