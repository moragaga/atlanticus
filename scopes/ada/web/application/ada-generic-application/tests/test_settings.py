from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.tools.persistence import ToolProjectionProvider, ToolSourceProvider
from atlanticus.connectivity.storage import (
    StorageConnectionStringCredential,
    StorageSasCredential,
)


def test_local_settings_build_tool_persistence_contract(tmp_path: Path) -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
        }
    )

    persistence = settings.tool_persistence_settings()

    assert settings.application_namespace == 'conciencia_situacional'
    assert persistence.namespace.application_namespace == 'conciencia_situacional'
    assert persistence.namespace.tool_namespace == 'operaciones_integradas'
    assert persistence.source_provider is ToolSourceProvider.LOCAL
    assert persistence.projection_provider is ToolProjectionProvider.LOCAL
    assert persistence.local_base_root == tmp_path
    assert settings.storage_settings() is None
    assert settings.cosmos_settings() is None


def test_blob_connection_string_and_cosmos_settings_are_provider_scoped() -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': 'production',
            'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
            'ADA_TOOL_SOURCE_PROVIDER': 'blob',
            'ADA_TOOL_PROJECTION_PROVIDER': 'cosmos',
            'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME': 'configuration',
            'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_TOOL_PROJECTION_COSMOS_ENDPOINT': 'https://cosmos.example.test',
            'ADA_TOOL_PROJECTION_COSMOS_KEY': 'cosmos-key',
            'ADA_TOOL_PROJECTION_COSMOS_DATABASE_NAME': 'configuration',
            'ADA_TOOL_PROJECTION_COSMOS_CONTAINER_NAME': 'tool-projection',
        }
    )

    storage = settings.storage_settings()
    cosmos = settings.cosmos_settings()

    assert storage is not None
    assert isinstance(storage.credential, StorageConnectionStringCredential)
    assert cosmos is not None
    assert cosmos.endpoint == 'https://cosmos.example.test'
    assert cosmos.database_name == 'configuration'


def test_blob_sas_settings_preserve_supported_storage_contract() -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
            'ADA_TOOL_SOURCE_PROVIDER': 'blob',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': '/tmp/atlanticus',
            'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME': 'configuration',
            'ADA_TOOL_SOURCE_BLOB_ACCOUNT_URL': 'http://127.0.0.1:10000/devstoreaccount1',
            'ADA_TOOL_SOURCE_BLOB_SAS_TOKEN': 'sig=local',
        }
    )

    storage = settings.storage_settings()

    assert storage is not None
    assert isinstance(storage.credential, StorageSasCredential)
    assert storage.credential.allow_insecure_http is True


def test_local_provider_requires_absolute_base_root() -> None:
    with pytest.raises(ValidationError, match='ADA_TOOL_LOCAL_BASE_ROOT must be an absolute path'):
        AdaGenericSettings.from_mapping(
            {
                'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
                'ADA_TOOL_SOURCE_PROVIDER': 'local',
                'ADA_TOOL_PROJECTION_PROVIDER': 'local',
                'ADA_TOOL_LOCAL_BASE_ROOT': '.runtime',
            }
        )


def test_blob_provider_rejects_ambiguous_credentials() -> None:
    with pytest.raises(ValidationError, match='connection string or SAS credentials, not both'):
        AdaGenericSettings.from_mapping(
            {
                'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
                'ADA_TOOL_SOURCE_PROVIDER': 'blob',
                'ADA_TOOL_PROJECTION_PROVIDER': 'local',
                'ADA_TOOL_LOCAL_BASE_ROOT': '/tmp/atlanticus',
                'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME': 'configuration',
                'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING': 'UseDevelopmentStorage=true',
                'ADA_TOOL_SOURCE_BLOB_ACCOUNT_URL': 'http://127.0.0.1:10000/devstoreaccount1',
                'ADA_TOOL_SOURCE_BLOB_SAS_TOKEN': 'sig=local',
            }
        )
