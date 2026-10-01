from __future__ import annotations

import getpass
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    open_local_configuration_manager,
)
from ada_command_center.web.application.generic.application import create_application
from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.manager import ManagerPrincipal
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
    if reader.manager_provider != 'local':
        raise RuntimeError('Command Center Generic Application 0.1.0 requires local Manager')
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
    with open_local_configuration_manager(
        reader=reader,
        principal_provider=lambda: principal,
        base_root=base_root,
    ) as dependencies:
        yield create_application(dependencies, identity_provider=identity)


def _resolve_local_subject_id(explicit_subject_id: str | None) -> str:
    resolved = (
        explicit_subject_id or os.getenv(_LOCAL_SUBJECT_VARIABLE) or f'local:{getpass.getuser()}'
    )
    normalized = resolved.strip()
    if not normalized:
        raise ValueError('Local Command Center subject id must not be empty')
    return normalized
