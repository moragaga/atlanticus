from pathlib import Path

import pytest

from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.persistence import (
    ToolPersistenceSettings,
    ToolProjectionProvider,
    ToolSourceProvider,
)


def _namespace() -> AdaStorageNamespace:
    return AdaStorageNamespace(
        application_namespace='conciencia_situacional',
        tool_namespace='mina',
    )


def test_local_provider_requires_absolute_root() -> None:
    with pytest.raises(ValueError, match='absolute'):
        ToolPersistenceSettings(
            namespace=_namespace(),
            source_provider=ToolSourceProvider.LOCAL,
            projection_provider=ToolProjectionProvider.LOCAL,
            local_base_root=Path('relative'),
        )


def test_blob_provider_requires_container_name(tmp_path: Path) -> None:
    with pytest.raises((TypeError, ValueError)):
        ToolPersistenceSettings(
            namespace=_namespace(),
            source_provider=ToolSourceProvider.BLOB,
            projection_provider=ToolProjectionProvider.LOCAL,
            local_base_root=tmp_path,
        )


def test_cosmos_provider_requires_container_name(tmp_path: Path) -> None:
    with pytest.raises((TypeError, ValueError)):
        ToolPersistenceSettings(
            namespace=_namespace(),
            source_provider=ToolSourceProvider.LOCAL,
            projection_provider=ToolProjectionProvider.COSMOS,
            local_base_root=tmp_path,
        )
