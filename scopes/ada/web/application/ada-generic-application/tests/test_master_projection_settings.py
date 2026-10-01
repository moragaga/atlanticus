from __future__ import annotations

from pathlib import Path

from ada.web.application.generic.settings import (
    MASTER_PROJECTION_RELATIVE_PATH,
    AdaGenericSettings,
    AdaPersistenceMode,
)


def test_local_master_material_location_is_derived_from_application_namespace(
    tmp_path: Path,
) -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_APPLICATION_NAMESPACE': 'app',
            'ADA_TOOL_NAMESPACE': 'tool',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
        }
    )

    assert settings.persistence_mode is AdaPersistenceMode.LOCAL
    assert settings.master_projection_local_path() == (
        tmp_path / 'app' / MASTER_PROJECTION_RELATIVE_PATH
    )


def test_durable_master_material_blob_is_application_scoped_not_tool_scoped() -> None:
    common = {
        'ADA_PERSISTENCE_MODE': 'durable',
        'ADA_APPLICATION_NAMESPACE': 'app',
        'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME': 'configuration',
        'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING': 'UseDevelopmentStorage=true',
        'ADA_TOOL_PROJECTION_COSMOS_ENDPOINT': 'http://localhost:8081',
        'ADA_TOOL_PROJECTION_COSMOS_KEY': 'test-only',
        'ADA_TOOL_PROJECTION_COSMOS_DATABASE_NAME': 'ada',
    }
    first = AdaGenericSettings.from_mapping({**common, 'ADA_TOOL_NAMESPACE': 'mine'})
    second = AdaGenericSettings.from_mapping({**common, 'ADA_TOOL_NAMESPACE': 'plant'})

    assert first.master_projection_blob_name() == f'app/{MASTER_PROJECTION_RELATIVE_PATH}'
    assert second.master_projection_blob_name() == first.master_projection_blob_name()


def test_legacy_master_material_path_no_longer_changes_runtime_location(tmp_path: Path) -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_APPLICATION_NAMESPACE': 'app',
            'ADA_TOOL_NAMESPACE': 'tool',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
            'ADA_MASTER_PROJECTION_MATERIAL_PATH': '/legacy/manual.zip',
        }
    )

    assert settings.master_projection_local_path() == (
        tmp_path / 'app' / MASTER_PROJECTION_RELATIVE_PATH
    )
