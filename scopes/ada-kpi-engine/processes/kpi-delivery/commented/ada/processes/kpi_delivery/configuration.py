# Espejo pedagógico del módulo productivo.
# Los comentarios explican la responsabilidad de la frontera sin alterar su semántica.
# Traduce estrictamente el documento durable del KPI Registry al modelo interno de Delivery.
# Esta frontera conoce el contrato Cosmos publicado, pero no depende de paquetes del frontend/Web.
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada.kpis.delivery import (
    KpiDeliveryBinding,
    KpiDeliveryConfiguration,
    KpiDeliveryValidationError,
)
from ada.processes.kpi_delivery.errors import KpiDeliveryConfigurationError
from ada.processes.kpi_delivery.storage import (
    KPI_REGISTRY_CONTAINER_SPEC,
    KPI_REGISTRY_PARTITION_VALUE,
)
from atlanticus.connectivity.cosmos import CosmosClient

KPI_REGISTRY_DOCUMENT_TYPE = 'ada_kpi_registry_projection_record'
KPI_REGISTRY_SCHEMA_VERSION = 1
KPI_REGISTRY_SOURCE_KEY = 'kpis'

# El identificador físico sigue el mismo contrato de identidad del productor: prefijo estable + SHA-256 del SourceKey.


def _registry_item_id(source_key: str) -> str:
    digest = hashlib.sha256(source_key.encode('utf-8')).hexdigest()
    return f'ada-kpi-registry-projection-{digest}'


KPI_REGISTRY_ITEM_ID = _registry_item_id(KPI_REGISTRY_SOURCE_KEY)


@dataclass(slots=True)
class KpiDeliveryRegistryRepository:
    client: CosmosClient

    def read(self) -> KpiDeliveryConfiguration:
        document = self.client.find_item(
            container_name=KPI_REGISTRY_CONTAINER_SPEC.name,
            item_id=KPI_REGISTRY_ITEM_ID,
            partition_key=KPI_REGISTRY_PARTITION_VALUE,
        )
        if document is None:
            raise KpiDeliveryConfigurationError('KPI Registry projection was not found')
        return _configuration_from_document(document)


def _configuration_from_document(document: Mapping[str, Any]) -> KpiDeliveryConfiguration:
    if not isinstance(document, Mapping):
        raise KpiDeliveryConfigurationError('KPI Registry projection must be an object')
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
        raise KpiDeliveryConfigurationError(
            'KPI Registry projection contains unexpected or missing fields'
        )
    if document['id'] != KPI_REGISTRY_ITEM_ID:
        raise KpiDeliveryConfigurationError('KPI Registry projection id is invalid')
    if document['partition_key'] != KPI_REGISTRY_PARTITION_VALUE:
        raise KpiDeliveryConfigurationError('KPI Registry projection partition_key is invalid')
    if document['document_type'] != KPI_REGISTRY_DOCUMENT_TYPE:
        raise KpiDeliveryConfigurationError('KPI Registry projection document_type is invalid')
    if document['schema_version'] != KPI_REGISTRY_SCHEMA_VERSION:
        raise KpiDeliveryConfigurationError('KPI Registry projection schema_version is invalid')
    if document['source_key'] != KPI_REGISTRY_SOURCE_KEY:
        raise KpiDeliveryConfigurationError('KPI Registry projection source_key is invalid')
    revision = _required_text(document['source_release_id'], 'source_release_id')
    tool_revision = _tool_projection_revision(document['dependencies'])
    payload = document['payload']
    if not isinstance(payload, Mapping) or set(payload) != {'bindings'}:
        raise KpiDeliveryConfigurationError('KPI Registry projection payload is invalid')
    raw_bindings = payload['bindings']
    if not isinstance(raw_bindings, list):
        raise KpiDeliveryConfigurationError('KPI Registry bindings must be an array')
    try:
        bindings = tuple(
            _binding_from_payload(value, index) for index, value in enumerate(raw_bindings)
        )
        return KpiDeliveryConfiguration(
            revision=revision,
            tool_projection_revision=tool_revision,
            bindings=bindings,
        )
    except (KpiDeliveryValidationError, TypeError) as error:
        raise KpiDeliveryConfigurationError(str(error)) from error


def _tool_projection_revision(value: object) -> str:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], Mapping):
        raise KpiDeliveryConfigurationError(
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
        raise KpiDeliveryConfigurationError('KPI Registry dependency contract is invalid')
    if not isinstance(dependency['dependencies'], list):
        raise KpiDeliveryConfigurationError('KPI Registry dependency contract is invalid')
    return _required_text(dependency['source_release_id'], 'dependencies[0].source_release_id')


def _binding_from_payload(value: object, index: int) -> KpiDeliveryBinding:
    if not isinstance(value, Mapping):
        raise KpiDeliveryConfigurationError(f'KPI Registry binding {index} must be an object')
    expected = {
        'kpi_key',
        'destination_keys',
        'latest_enabled',
        'series_enabled',
        'series_hours',
    }
    if set(value) != expected:
        raise KpiDeliveryConfigurationError(
            f'KPI Registry binding {index} contains unexpected or missing fields'
        )
    destinations = value['destination_keys']
    if not isinstance(destinations, list):
        raise KpiDeliveryConfigurationError(
            f'KPI Registry binding {index} destination_keys must be an array'
        )
    latest_enabled = _required_bool(value['latest_enabled'], f'bindings[{index}].latest_enabled')
    series_enabled = _required_bool(value['series_enabled'], f'bindings[{index}].series_enabled')
    series_hours = _series_hours(value['series_hours'], enabled=series_enabled, index=index)
    return KpiDeliveryBinding(
        key=_required_text(value['kpi_key'], f'bindings[{index}].kpi_key'),
        destination_keys=tuple(destinations),
        latest_enabled=latest_enabled,
        series_enabled=series_enabled,
        series_hours=series_hours,
    )


def _series_hours(value: object, *, enabled: bool, index: int) -> int | None:
    if not enabled:
        if value is not None:
            raise KpiDeliveryConfigurationError(
                f'bindings[{index}].series_hours must be empty when series is disabled'
            )
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 24:
        raise KpiDeliveryConfigurationError(
            f'bindings[{index}].series_hours must be between 1 and 24 when series is enabled'
        )
    return value


def _required_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise KpiDeliveryConfigurationError(f'{field_name} must be boolean')
    return value


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KpiDeliveryConfigurationError(f'{field_name} must be a non-empty string')
    if value != value.strip():
        raise KpiDeliveryConfigurationError(f'{field_name} must not contain surrounding whitespace')
    return value
