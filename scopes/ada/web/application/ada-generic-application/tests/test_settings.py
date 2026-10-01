from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ada.web.application.generic.settings import (
    MASTER_PROJECTION_RELATIVE_PATH,
    AdaGenericSettings,
    AdaPersistenceMode,
)
from ada.web.kpis.collector import (
    DEFAULT_KPI_LATEST_DELIVERY_CONTAINER,
    DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER,
)
from ada.web.tools.persistence import ToolProjectionProvider, ToolSourceProvider
from ada.web.tools.projection.cosmos import TOOL_PROJECTION_STORAGE_RESOURCE
from atlanticus.connectivity.storage import (
    StorageConnectionStringCredential,
    StorageSasCredential,
)


def _durable_values() -> dict[str, str]:
    return {
        'ADA_PERSISTENCE_MODE': 'durable',
        'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
        'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME': 'configuration',
        'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING': 'UseDevelopmentStorage=true',
        'ADA_TOOL_PROJECTION_COSMOS_ENDPOINT': 'https://cosmos.example.test',
        'ADA_TOOL_PROJECTION_COSMOS_KEY': 'cosmos-key',
        'ADA_TOOL_PROJECTION_COSMOS_DATABASE_NAME': 'configuration',
    }


def test_local_settings_derive_local_tool_persistence(tmp_path: Path) -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
        }
    )

    persistence = settings.tool_persistence_settings()

    assert settings.persistence_mode is AdaPersistenceMode.LOCAL
    assert settings.application_namespace == 'conciencia_situacional'
    assert persistence.namespace.application_namespace == 'conciencia_situacional'
    assert persistence.namespace.tool_namespace == 'operaciones_integradas'
    assert persistence.source_provider is ToolSourceProvider.LOCAL
    assert persistence.projection_provider is ToolProjectionProvider.LOCAL
    assert persistence.local_base_root == tmp_path
    assert persistence.cosmos_container_name is None
    assert settings.storage_settings() is None
    assert settings.tool_projection_cosmos_settings() is None
    assert settings.kpi_delivery_cosmos_settings() is None


def test_durable_mode_derives_blob_and_cosmos_providers() -> None:
    settings = AdaGenericSettings.from_mapping(
        {'ATLANTICUS_ENVIRONMENT': 'production', **_durable_values()}
    )

    storage = settings.storage_settings()
    cosmos = settings.tool_projection_cosmos_settings()
    persistence = settings.tool_persistence_settings()

    assert settings.persistence_mode is AdaPersistenceMode.DURABLE
    assert settings.tool_source_provider is ToolSourceProvider.BLOB
    assert settings.tool_projection_provider is ToolProjectionProvider.COSMOS
    assert storage is not None
    assert isinstance(storage.credential, StorageConnectionStringCredential)
    assert cosmos is not None
    assert cosmos.endpoint == 'https://cosmos.example.test'
    assert cosmos.database_name == 'configuration'
    assert persistence.cosmos_container_name == TOOL_PROJECTION_STORAGE_RESOURCE.default_physical_name


def test_legacy_provider_variables_do_not_select_persistence(tmp_path: Path) -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
            'ADA_TOOL_SOURCE_PROVIDER': 'blob',
            'ADA_TOOL_PROJECTION_PROVIDER': 'cosmos',
        }
    )

    assert settings.persistence_mode is AdaPersistenceMode.LOCAL
    assert settings.tool_source_provider is ToolSourceProvider.LOCAL
    assert settings.tool_projection_provider is ToolProjectionProvider.LOCAL


def test_kpi_delivery_cosmos_connection_remains_independent(tmp_path: Path) -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
            'COSMOS_CONSUMPTION_ENDPOINT': 'https://consumption.example.test',
            'COSMOS_CONSUMPTION_KEY': 'consumption-key',
            'COSMOS_CONSUMPTION_DATABASE_NAME': 'consumption',
        }
    )

    cosmos = settings.kpi_delivery_cosmos_settings()
    reader = settings.kpi_delivery_reader_settings()

    assert settings.tool_projection_cosmos_settings() is None
    assert cosmos is not None
    assert cosmos.endpoint == 'https://consumption.example.test'
    assert cosmos.database_name == 'consumption'
    assert reader.latest_container_name == DEFAULT_KPI_LATEST_DELIVERY_CONTAINER
    assert reader.timeseries_container_name == DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER


def test_kpi_delivery_reader_uses_collector_container_defaults(tmp_path: Path) -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
        }
    )

    reader = settings.kpi_delivery_reader_settings()

    assert reader.latest_container_name == DEFAULT_KPI_LATEST_DELIVERY_CONTAINER
    assert reader.timeseries_container_name == DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER


def test_cosmos_resource_names_are_internal_not_environment_configuration() -> None:
    settings = AdaGenericSettings.from_mapping(_durable_values())
    persistence = settings.tool_persistence_settings()
    reader = settings.kpi_delivery_reader_settings()

    assert persistence.cosmos_container_name == TOOL_PROJECTION_STORAGE_RESOURCE.default_physical_name
    assert reader.latest_container_name == DEFAULT_KPI_LATEST_DELIVERY_CONTAINER
    assert reader.timeseries_container_name == DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER


def test_partial_kpi_delivery_cosmos_connection_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(
        ValidationError,
        match='COSMOS_CONSUMPTION_KEY is required when KPI delivery Cosmos is configured',
    ):
        AdaGenericSettings.from_mapping(
            {
                'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
                'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
                'COSMOS_CONSUMPTION_ENDPOINT': 'https://consumption.example.test',
            }
        )


def test_blob_sas_settings_preserve_supported_storage_contract() -> None:
    values = _durable_values()
    values.pop('ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING')
    values.update(
        {
            'ADA_TOOL_SOURCE_BLOB_ACCOUNT_URL': 'http://127.0.0.1:10000/devstoreaccount1',
            'ADA_TOOL_SOURCE_BLOB_SAS_TOKEN': 'sig=local',
        }
    )
    settings = AdaGenericSettings.from_mapping(values)

    storage = settings.storage_settings()

    assert storage is not None
    assert isinstance(storage.credential, StorageSasCredential)
    assert storage.credential.allow_insecure_http is True


def test_local_base_root_defaults_and_relative_override_are_resolved(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    default = AdaGenericSettings.from_mapping({'ADA_TOOL_NAMESPACE': 'operaciones_integradas'})
    overridden = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
            'ADA_TOOL_LOCAL_BASE_ROOT': 'custom-runtime',
        }
    )

    assert default.local_base_root() == tmp_path / '.runtime/ada'
    assert overridden.local_base_root() == tmp_path / 'custom-runtime'
    assert default.master_projection_local_path() == (
        tmp_path / '.runtime/ada/conciencia_situacional' / MASTER_PROJECTION_RELATIVE_PATH
    )


def test_durable_mode_rejects_ambiguous_blob_credentials() -> None:
    values = _durable_values()
    values.update(
        {
            'ADA_TOOL_SOURCE_BLOB_ACCOUNT_URL': 'http://127.0.0.1:10000/devstoreaccount1',
            'ADA_TOOL_SOURCE_BLOB_SAS_TOKEN': 'sig=local',
        }
    )
    with pytest.raises(ValidationError, match='connection string or SAS credentials, not both'):
        AdaGenericSettings.from_mapping(values)


def test_durable_mode_requires_complete_cosmos_connection() -> None:
    values = _durable_values()
    values.pop('ADA_TOOL_PROJECTION_COSMOS_KEY')
    with pytest.raises(ValidationError, match='ADA_TOOL_PROJECTION_COSMOS_KEY is required'):
        AdaGenericSettings.from_mapping(values)


def test_unknown_persistence_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AdaGenericSettings.from_mapping(
            {'ADA_PERSISTENCE_MODE': 'unknown', 'ADA_TOOL_NAMESPACE': 'operaciones_integradas'}
        )
