from __future__ import annotations

import os
from contextlib import ExitStack

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic.bootstrap import create_operational_application_runtime
from ada.web.application.generic.manager_deployment import open_durable_manager
from ada.web.application.generic.settings import AdaGenericSettings, AdaPersistenceMode
from atlanticus.web.application import run_web_application
from atlanticus.web.dash_worker import prepare_dash_worker
from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.models import WebApplicationRuntime
from atlanticus.web.users.local import select_local_user

from application.composition import create_composition
from application.master_projection.reader import (
    BlobMasterMaterialReader,
    StarterMasterMaterialReader,
)


class AdaWorkerRuntime:
    def __init__(self, application: WebApplicationRuntime, resources: ExitStack) -> None:
        self.application = application
        self.server = application.server
        self._resources = resources

    def close(self) -> None:
        self._resources.close()


def _local_identity() -> LocalIdentityProvider:
    subject = os.getenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID') or select_local_user().subject_id
    return LocalIdentityProvider(subject_id=subject)


def _production_identity() -> IdentityProvider:
    from application.production import create_identity_provider

    provider = create_identity_provider()
    if not isinstance(provider, IdentityProvider) or not provider.production_ready:
        raise IdentityConfigurationError('The host must supply a production-ready IdentityProvider')
    provider.validate_configuration()
    return provider


def create_worker_runtime() -> AdaWorkerRuntime:
    settings = AdaGenericSettings()
    resources = ExitStack()
    try:
        if settings.persistence_mode is AdaPersistenceMode.LOCAL:
            material_reader = StarterMasterMaterialReader(settings.master_projection_local_path())
            application = create_operational_application_runtime(
                settings=settings,
                manager_stores=create_local_configuration_manager_stores(),
                identity_provider=_local_identity(),
                manager_source_name='Local Source',
                manager_projection_name='Local Projection',
                composition_factory=create_composition,
                master_material_reader=material_reader,
            )
        else:
            deployment = resources.enter_context(open_durable_manager(settings))
            resource = deployment.resources.application_source
            material_reader = BlobMasterMaterialReader(
                client=deployment.connections.storage[resource.connection_ref],
                container_name=resource.container_name,
                blob_name=settings.master_projection_blob_name(),
            )
            identity = _production_identity() if settings.environment.is_production else _local_identity()
            application = create_operational_application_runtime(
                settings=settings,
                manager_stores=deployment.stores,
                identity_provider=identity,
                manager_source_name='Blob Storage',
                manager_projection_name='Cosmos DB',
                composition_factory=create_composition,
                master_material_reader=material_reader,
            )
        prepare_dash_worker(application.dash)
        return AdaWorkerRuntime(application, resources)
    except Exception:
        resources.close()
        raise


def run_application() -> None:
    worker = create_worker_runtime()
    try:
        run_web_application(worker.application)
    finally:
        worker.close()
