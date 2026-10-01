from __future__ import annotations

# Espejo pedagógico: mismo comportamiento productivo con contexto explicativo en español.

import os

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic.bootstrap import (
    AdaOperationalCompositionFactory,
    create_operational_application_runtime,
)
from ada.web.application.generic.manager_deployment import (
    ManagerStartupOptions,
    open_durable_manager,
)
from ada.web.application.generic.settings import AdaGenericSettings, AdaPersistenceMode
from atlanticus.web.application import run_web_application
from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.users.local import select_local_user


def _local_identity() -> LocalIdentityProvider:
    selected = os.getenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID') or select_local_user().subject_id
    return LocalIdentityProvider(subject_id=selected)


def run_operational_application(
    *,
    composition_factory: AdaOperationalCompositionFactory | None = None,
) -> None:
    extension = (
        {'composition_factory': composition_factory}
        if composition_factory is not None
        else {}
    )
    settings = AdaGenericSettings()
    provider = ManagerStartupOptions().provider
    if provider is AdaPersistenceMode.LOCAL:
        if not settings.environment.is_local:
            raise IdentityConfigurationError('Local persistence is unavailable in production')
        runtime = create_operational_application_runtime(
            settings=settings,
            manager_stores=create_local_configuration_manager_stores(),
            identity_provider=_local_identity(),
            manager_source_name='Local Source',
            manager_projection_name='Local Projection',
            **extension,
        )
        run_web_application(runtime)
        return
    if not settings.environment.is_local:
        raise IdentityConfigurationError(
            'Production durable Manager requires an injected production identity provider'
        )
    with open_durable_manager(settings) as deployment:
        runtime = create_operational_application_runtime(
            settings=settings,
            manager_stores=deployment.stores,
            identity_provider=_local_identity(),
            manager_source_name='Blob Storage',
            manager_projection_name='Cosmos DB',
            **extension,
        )
        run_web_application(runtime)


def main() -> None:
    run_operational_application()


if __name__ == '__main__':
    main()
