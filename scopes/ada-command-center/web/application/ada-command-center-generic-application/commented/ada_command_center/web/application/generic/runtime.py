# Espejo pedagógico: conserva exactamente el comportamiento del archivo productivo.
# Los comentarios documentan intención, ownership y flujo sin agregar compatibilidad ni lógica alternativa.
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ada_command_center.web.application.configuration_manager.catalog_configuration import ManagerConfigurationReader
from ada_command_center.web.application.configuration_manager.durable_runtime import (
    open_durable_configuration_manager,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    open_local_configuration_manager,
)
from ada_command_center.web.application.generic.application import create_application
from ada_command_center.web.application.generic.manager_principal import ManagerPrincipalBinding
from atlanticus.web.identity.access import AccessRuntime
from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.models import WebApplicationRuntime
from atlanticus.web.users.local import LOCAL_USERS
from atlanticus.web.users.runtime import UsersRuntime

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
    identity = LocalIdentityProvider(subject_id=resolved_subject)
    users_runtime = UsersRuntime()
    principal = ManagerPrincipalBinding(
        access_runtime=AccessRuntime(),
        users_runtime=users_runtime,
        trusted_local_users=True,
    )

    if reader.manager_provider == 'local':
        manager = open_local_configuration_manager(
            reader=reader,
            principal_provider=principal,
            base_root=base_root,
        )
    else:
        manager = open_durable_configuration_manager(
            reader=reader,
            principal_provider=principal,
        )
    with manager as dependencies:
        yield create_application(
            dependencies,
            identity_provider=identity,
            users_runtime=users_runtime,
            environment=reader.environment,
        )


def _resolve_local_subject_id(explicit_subject_id: str | None) -> str:
    resolved = explicit_subject_id or os.getenv(_LOCAL_SUBJECT_VARIABLE) or LOCAL_USERS[0].subject_id
    normalized = resolved.strip()
    if not normalized:
        raise ValueError('Local Command Center subject id must not be empty')
    return normalized
