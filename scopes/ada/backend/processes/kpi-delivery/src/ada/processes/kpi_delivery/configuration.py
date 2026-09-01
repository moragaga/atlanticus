from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada.kpis.delivery import (
    KpiDeliveryBinding,
    KpiDeliveryConfiguration,
    KpiDeliveryValidationError,
)
from ada.processes.kpi_delivery.errors import KpiDeliveryConfigurationError
from atlanticus.connectivity.cosmos import CosmosClient

KPI_CONFIGURATION_DOCUMENT_TYPE = 'ada_kpi_configuration_projection'
KPI_CONFIGURATION_SCHEMA_VERSION = 1


@dataclass(slots=True)
class KpiDeliveryConfigurationRepository:
    client: CosmosClient
    container_name: str
    item_id: str
    partition_key: str

    def read(self) -> KpiDeliveryConfiguration:
        document = self.client.find_item(
            container_name=self.container_name,
            item_id=self.item_id,
            partition_key=self.partition_key,
        )
        if document is None:
            raise KpiDeliveryConfigurationError('KPI delivery configuration was not found')
        return _configuration_from_document(
            document,
            expected_id=self.item_id,
            expected_partition_key=self.partition_key,
        )


def _configuration_from_document(
    document: Mapping[str, Any],
    *,
    expected_id: str,
    expected_partition_key: str,
) -> KpiDeliveryConfiguration:
    if not isinstance(document, Mapping):
        raise KpiDeliveryConfigurationError('KPI delivery configuration must be an object')
    expected_fields = {
        'id',
        'partition_key',
        'document_type',
        'schema_version',
        'revision',
        'tool_projection_revision',
        'configuration',
    }
    if set(document) != expected_fields:
        raise KpiDeliveryConfigurationError(
            'KPI delivery configuration contains unexpected or missing fields'
        )
    if document['id'] != expected_id:
        raise KpiDeliveryConfigurationError('KPI delivery configuration id is invalid')
    if document['partition_key'] != expected_partition_key:
        raise KpiDeliveryConfigurationError('KPI delivery configuration partition_key is invalid')
    if document['document_type'] != KPI_CONFIGURATION_DOCUMENT_TYPE:
        raise KpiDeliveryConfigurationError('KPI delivery configuration document_type is invalid')
    if document['schema_version'] != KPI_CONFIGURATION_SCHEMA_VERSION:
        raise KpiDeliveryConfigurationError('KPI delivery configuration schema_version is invalid')
    payload = document['configuration']
    if not isinstance(payload, Mapping) or set(payload) != {'bindings'}:
        raise KpiDeliveryConfigurationError('KPI delivery configuration payload is invalid')
    raw_bindings = payload['bindings']
    if not isinstance(raw_bindings, list):
        raise KpiDeliveryConfigurationError('KPI delivery configuration bindings must be an array')
    try:
        bindings = tuple(
            _binding_from_payload(value, index) for index, value in enumerate(raw_bindings)
        )
        return KpiDeliveryConfiguration(
            revision=_required_text(document['revision'], 'revision'),
            tool_projection_revision=_optional_text(
                document['tool_projection_revision'], 'tool_projection_revision'
            ),
            bindings=bindings,
        )
    except (KpiDeliveryValidationError, TypeError) as error:
        raise KpiDeliveryConfigurationError(str(error)) from error


def _binding_from_payload(value: object, index: int) -> KpiDeliveryBinding:
    if not isinstance(value, Mapping):
        raise KpiDeliveryConfigurationError(
            f'KPI delivery configuration binding {index} must be an object'
        )
    expected = {
        'key',
        'destination_keys',
        'latest_enabled',
        'series_enabled',
        'series_hours',
    }
    if set(value) != expected:
        raise KpiDeliveryConfigurationError(
            f'KPI delivery configuration binding {index} contains unexpected or missing fields'
        )
    destinations = value['destination_keys']
    if not isinstance(destinations, list):
        raise KpiDeliveryConfigurationError(
            f'KPI delivery configuration binding {index} destination_keys must be an array'
        )
    return KpiDeliveryBinding(
        key=_required_text(value['key'], f'bindings[{index}].key'),
        destination_keys=tuple(destinations),
        latest_enabled=_required_bool(value['latest_enabled'], f'bindings[{index}].latest_enabled'),
        series_enabled=_required_bool(value['series_enabled'], f'bindings[{index}].series_enabled'),
        series_hours=value['series_hours'],
    )


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


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)
