from __future__ import annotations

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
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.application import run_web_application
from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.users.local import select_local_user


# La identidad local se selecciona solo donde el entorno permite usarla.
def _local_identity() -> LocalIdentityProvider:
    selected = (
        os.getenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID') or select_local_user().subject_id
    )
    return LocalIdentityProvider(subject_id=selected)


# La selección auto conserva el comportamiento anterior y durable es opt-in.
# Production durable requiere inyección externa; nunca se fabrica un Entra ficticio.
# La selección estándar mantiene exactamente los argumentos previos sin extensión.
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
    if provider == 'auto':
        provider = 'local' if settings.environment.is_local else 'disabled'
    if provider == 'local':
        if not settings.environment.is_local:
            raise IdentityConfigurationError('Local Manager is unavailable in production')
        runtime = create_operational_application_runtime(
            settings=settings,
            manager_stores=create_local_configuration_manager_stores(),
            identity_provider=_local_identity(),
            **extension,
        )
    elif provider == 'durable':
        if not settings.environment.is_local:
            raise IdentityConfigurationError(
                'Production durable Manager requires an injected production identity provider'
            )
# El contexto conserva clientes abiertos mientras se atienden solicitudes.
        with open_durable_manager(settings) as deployment:
            runtime = create_operational_application_runtime(
                settings=settings,
                manager_stores=deployment.stores,
                identity_provider=_local_identity(),
                **extension,
            )
            run_web_application(runtime)
        return
    else:
        runtime = create_operational_application_runtime(
            settings=settings,
            **extension,
        )
    run_web_application(runtime)


def main() -> None:
    run_operational_application()


if __name__ == '__main__':
    main()
