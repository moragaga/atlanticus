from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from ada.kpis.materialization.errors import KpiMaterializationContractError

KPI_REGISTRY_CONTAINER_NAME = 'ada-kpi-registry-projection'
KPI_REGISTRY_PARTITION_VALUE = 'kpi-registry'
KPI_REGISTRY_DOCUMENT_TYPE = 'ada_kpi_registry_projection_record'
KPI_REGISTRY_SCHEMA_VERSION = 1
KPI_REGISTRY_SOURCE_KEY = 'kpi-registry'
_TOOL_KEY_PATTERN = re.compile(r'[a-z][a-z0-9_]*\Z')


def _registry_item_id(source_key: str) -> str:
    digest = hashlib.sha256(source_key.encode('utf-8')).hexdigest()
    return f'ada-kpi-registry-projection-{digest}'


KPI_REGISTRY_ITEM_ID = _registry_item_id(KPI_REGISTRY_SOURCE_KEY)


def require_tool_key(value: object) -> str:
    if not isinstance(value, str) or _TOOL_KEY_PATTERN.fullmatch(value) is None:
        raise KpiMaterializationContractError('tool_key has an invalid format')
    return value


def validate_registry_projection(document: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise KpiMaterializationContractError('KPI Registry projection must be an object')
    expected_fields = {
        'id',
        'partition_key',
        'document_type',
        'schema_version',
        'source_key',
        'source_release_id',
        'source_published_at_utc',
        'projected_at_utc',
        'dependencies',
        'payload',
    }
    if set(document) != expected_fields:
        raise KpiMaterializationContractError(
            'KPI Registry projection contains unexpected or missing fields'
        )
    if document['id'] != KPI_REGISTRY_ITEM_ID:
        raise KpiMaterializationContractError('KPI Registry projection id is invalid')
    if document['partition_key'] != KPI_REGISTRY_PARTITION_VALUE:
        raise KpiMaterializationContractError('KPI Registry projection partition_key is invalid')
    if document['document_type'] != KPI_REGISTRY_DOCUMENT_TYPE:
        raise KpiMaterializationContractError('KPI Registry projection document_type is invalid')
    if document['schema_version'] != KPI_REGISTRY_SCHEMA_VERSION:
        raise KpiMaterializationContractError('KPI Registry projection schema_version is invalid')
    if document['source_key'] != KPI_REGISTRY_SOURCE_KEY:
        raise KpiMaterializationContractError('KPI Registry projection source_key is invalid')
    _required_text(document['source_release_id'], 'source_release_id')
    _validate_dependency(document['dependencies'])
    _validate_payload(document['payload'])
    return deepcopy(dict(document))


def materialize_registry(*, tool_key: str, projection: Mapping[str, Any]) -> dict[str, Any]:
    resolved_tool_key = require_tool_key(tool_key)
    validated = validate_registry_projection(projection)
    return {'tool_key': resolved_tool_key, **validated}


def validate_materialized_registry(
    document: Mapping[str, Any],
    *,
    expected_tool_key: str | None = None,
) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise KpiMaterializationContractError('Materialized KPI Registry must be an object')
    expected_fields = {
        'tool_key',
        'id',
        'partition_key',
        'document_type',
        'schema_version',
        'source_key',
        'source_release_id',
        'source_published_at_utc',
        'projected_at_utc',
        'dependencies',
        'payload',
    }
    if set(document) != expected_fields:
        raise KpiMaterializationContractError(
            'Materialized KPI Registry contains unexpected or missing fields'
        )
    tool_key = require_tool_key(document['tool_key'])
    if expected_tool_key is not None and tool_key != require_tool_key(expected_tool_key):
        raise KpiMaterializationContractError('Materialized KPI Registry tool_key mismatch')
    projection = {key: value for key, value in document.items() if key != 'tool_key'}
    validated = validate_registry_projection(projection)
    return {'tool_key': tool_key, **validated}


def _validate_dependency(value: object) -> None:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], Mapping):
        raise KpiMaterializationContractError(
            'KPI Registry projection must contain exactly one dependency'
        )
    dependency = value[0]
    expected_fields = {
        'source_key',
        'source_release_id',
        'source_published_at_utc',
        'dependencies',
    }
    if set(dependency) != expected_fields:
        raise KpiMaterializationContractError('KPI Registry dependency contract is invalid')
    _required_text(dependency['source_release_id'], 'dependencies[0].source_release_id')
    if not isinstance(dependency['dependencies'], list):
        raise KpiMaterializationContractError('KPI Registry dependency contract is invalid')


def _validate_payload(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) != {'bindings'}:
        raise KpiMaterializationContractError('KPI Registry projection payload is invalid')
    bindings = value['bindings']
    if not isinstance(bindings, list):
        raise KpiMaterializationContractError('KPI Registry bindings must be an array')
    seen: set[str] = set()
    for index, binding in enumerate(bindings):
        if not isinstance(binding, Mapping):
            raise KpiMaterializationContractError(f'KPI Registry binding {index} must be an object')
        expected = {
            'kpi_key',
            'destination_keys',
            'latest_enabled',
            'series_enabled',
            'series_hours',
        }
        if set(binding) != expected:
            raise KpiMaterializationContractError(
                f'KPI Registry binding {index} contains unexpected or missing fields'
            )
        kpi_key = _required_text(binding['kpi_key'], f'bindings[{index}].kpi_key')
        if kpi_key in seen:
            raise KpiMaterializationContractError('KPI Registry contains duplicate KPI keys')
        seen.add(kpi_key)
        destinations = binding['destination_keys']
        if not isinstance(destinations, list):
            raise KpiMaterializationContractError(
                f'bindings[{index}].destination_keys must be an array'
            )
        destination_keys = tuple(
            _required_text(item, f'bindings[{index}].destination_keys') for item in destinations
        )
        if not destination_keys:
            raise KpiMaterializationContractError(
                f'bindings[{index}].destination_keys must not be empty'
            )
        if len(destination_keys) != len(set(destination_keys)):
            raise KpiMaterializationContractError(
                f'bindings[{index}].destination_keys contains duplicates'
            )
        _required_bool(binding['latest_enabled'], f'bindings[{index}].latest_enabled')
        series_enabled = _required_bool(
            binding['series_enabled'], f'bindings[{index}].series_enabled'
        )
        _validate_series_hours(
            binding['series_hours'],
            enabled=series_enabled,
            index=index,
        )


def _validate_series_hours(value: object, *, enabled: bool, index: int) -> None:
    if not enabled:
        if value is not None:
            raise KpiMaterializationContractError(
                f'bindings[{index}].series_hours must be empty when series is disabled'
            )
        return
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 24:
        raise KpiMaterializationContractError(
            f'bindings[{index}].series_hours must be between 1 and 24 when series is enabled'
        )


def _required_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise KpiMaterializationContractError(f'{field_name} must be boolean')
    return value


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KpiMaterializationContractError(f'{field_name} must be a non-empty string')
    if value != value.strip():
        raise KpiMaterializationContractError(
            f'{field_name} must not contain surrounding whitespace'
        )
    return value
