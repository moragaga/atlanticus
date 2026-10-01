# Espejo pedagógico equivalente al código productivo.
from __future__ import annotations

from pathlib import Path

from ada_command_center.web.application.configuration_manager.application import (
    create_configuration_manager_application,
)
from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.configuration_manager.durable_runtime import (
    open_durable_configuration_manager,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    open_local_configuration_manager,
)
from atlanticus.web.application import run_web_application
from atlanticus.web.manager import ManagerPrincipal


def main() -> None:
    reader = ManagerConfigurationReader(root=Path.cwd())
    if reader.environment.is_production:
        raise RuntimeError('Production Command Center requires an authenticated host')
    # El host temporal confía explícitamente en este principal sólo fuera de producción.
    # local no necesita una lista de *.manage: su semántica es administración total del Manager.
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        profile_keys=('local',),
        access_keys=(),
        administrative_override=True,
        is_local=True,
    )
    # El ambiente Web no decide si el proveedor de persistencia es local o durable.
    provider = (
        open_local_configuration_manager
        if reader.manager_provider == 'local'
        else open_durable_configuration_manager
    )
    with provider(reader=reader, principal_provider=lambda: principal) as dependencies:
        run_web_application(create_configuration_manager_application(dependencies))


if __name__ == '__main__':
    main()
