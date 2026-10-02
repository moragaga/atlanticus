from __future__ import annotations

import getpass
import os
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    STORAGE_CONTAINER_VARIABLE,
    ManagerConfigurationReader,
    catalog_storage_settings,
)
from ada_command_center.web.application.configuration_manager.durable_runtime import (
    open_durable_configuration_manager,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    open_local_configuration_manager,
)
from ada_command_center.web.application.generic.application import create_application
from ada_command_center.web.application.generic.master_projection.location import (
    COMMAND_CENTER_MASTER_BLOB_NAME,
    master_projection_local_path,
)
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.master_projection.reader import (
    BlobMasterMaterialReader,
    LocalMasterMaterialReader,
)
from atlanticus.web.models import WebApplicationRuntime

_LOCAL_SUBJECT_VARIABLE = 'ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID'


@contextmanager
def open_local_application(
    *,
    reader: ManagerConfigurationReader,
    base_root: Path | None = None,
    subject_id: str | None = None,
) -> Iterator[WebApplicationRuntime]:
    if reader.environment.is_production:
        raise IdentityConfigurationError(
            'Production Command Center requires an injected production identity provider'
        )
    resolved_subject = _resolve_local_subject_id(subject_id)
    principal = ManagerPrincipal(
        subject_id=resolved_subject,
        display_name='Administrador local',
        profile_keys=('local',),
        access_keys=(),
        administrative_override=True,
        is_local=True,
    )
    identity = LocalIdentityProvider(subject_id=resolved_subject)

    with ExitStack() as resources:
        if reader.manager_provider == 'local':
            root = (base_root if base_root is not None else Path.cwd() / '.runtime').expanduser()
            material_reader = LocalMasterMaterialReader(master_projection_local_path(root))
            manager = open_local_configuration_manager(
                reader=reader,
                principal_provider=lambda: principal,
                base_root=base_root,
            )
        else:
            values = reader.storage()
            storage = StorageClient(settings=catalog_storage_settings(values))
            resources.callback(storage.close)
            material_reader = BlobMasterMaterialReader(
                client=storage,
                container_name=values[STORAGE_CONTAINER_VARIABLE],
                blob_name=COMMAND_CENTER_MASTER_BLOB_NAME,
            )
            manager = open_durable_configuration_manager(
                reader=reader,
                principal_provider=lambda: principal,
            )
        with manager as dependencies:
            yield create_application(
                dependencies,
                identity_provider=identity,
                master_material_reader=material_reader,
                environment=reader.environment,
            )


def _resolve_local_subject_id(explicit_subject_id: str | None) -> str:
    resolved = (
        explicit_subject_id or os.getenv(_LOCAL_SUBJECT_VARIABLE) or f'local:{getpass.getuser()}'
    )
    normalized = resolved.strip()
    if not normalized:
        raise ValueError('Local Command Center subject id must not be empty')
    return normalized
