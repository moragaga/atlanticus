from __future__ import annotations

# Espejo pedagógico: mismo código ejecutable con comentarios en español.

import os
from contextlib import ExitStack

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic.bootstrap import create_operational_application_runtime
from ada.web.application.generic.host import run_operational_application
from ada.web.application.generic.manager_deployment import (
    ManagerStartupOptions,
    open_durable_manager,
)
from ada.web.application.generic.settings import AdaGenericSettings
from application.composition import create_composition
from atlanticus.web.dash_worker import prepare_dash_worker
from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.models import WebApplicationRuntime
from atlanticus.web.users.local import select_local_user


# Adaptador mínimo del runtime Flask con cierre de recursos durables por worker.
class AdaWorkerRuntime:
    def __init__(self, application: WebApplicationRuntime, resources: ExitStack) -> None:
        self.server = application.server
        self._resources = resources

    # Liberar conexiones gestionadas al finalizar cada worker.
    def close(self) -> None:
        self._resources.close()


# Seleccionar identidad de desarrollo sólo cuando el ambiente es local.
def _local_identity() -> LocalIdentityProvider:
    subject = os.getenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID') or select_local_user().subject_id
    return LocalIdentityProvider(subject_id=subject)


# El host aporta su integración Entra; nunca se sustituye por identidad local.
def _production_identity() -> IdentityProvider:
    from application.production import create_identity_provider

    provider = create_identity_provider()
    if not isinstance(provider, IdentityProvider) or not provider.production_ready:
        raise IdentityConfigurationError('The host must supply a production-ready IdentityProvider')
    provider.validate_configuration()
    return provider


# Crear un runtime por worker, con política explícita para local/durable/producción.
def create_worker_runtime() -> AdaWorkerRuntime:
    settings = AdaGenericSettings()
    provider = ManagerStartupOptions().provider
    if provider == 'auto':
        provider = 'local' if settings.environment.is_local else 'disabled'
    resources = ExitStack()
    try:
        if settings.environment.is_production:
            if provider != 'durable':
                raise IdentityConfigurationError('Production ADA requires durable Manager mode')
            identity = _production_identity()
            deployment = resources.enter_context(open_durable_manager(settings))
            application = create_operational_application_runtime(
                settings=settings,
                manager_stores=deployment.stores,
                identity_provider=identity,
                manager_source_name='Blob Storage',
                manager_projection_name='Cosmos DB',
                composition_factory=create_composition,
            )
        elif provider == 'local':
            application = create_operational_application_runtime(
                settings=settings,
                manager_stores=create_local_configuration_manager_stores(),
                identity_provider=_local_identity(),
                manager_source_name='Local Source',
                manager_projection_name='Local Projection',
                composition_factory=create_composition,
            )
        elif provider == 'durable':
            deployment = resources.enter_context(open_durable_manager(settings))
            application = create_operational_application_runtime(
                settings=settings,
                manager_stores=deployment.stores,
                identity_provider=_local_identity(),
                manager_source_name='Blob Storage',
                manager_projection_name='Cosmos DB',
                composition_factory=create_composition,
            )
        else:
            application = create_operational_application_runtime(
                settings=settings,
                composition_factory=create_composition,
            )
        # Preparar los recursos Dash dentro del worker y fallar antes de admitir tráfico.
        prepare_dash_worker(application.dash)
        return AdaWorkerRuntime(application, resources)
    except Exception:
        resources.close()
        raise


# Mantener ejecución no Docker como camino independiente de Gunicorn.
def run_application() -> None:
    run_operational_application(composition_factory=create_composition)
