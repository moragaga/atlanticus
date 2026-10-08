from __future__ import annotations

import os
from dataclasses import replace
from functools import partial
from importlib.metadata import version
from pathlib import Path

from ada_command_center.web.application.configuration_manager import (
    MANAGER_ROUTE_PREFIX,
    ConfigurationManagerDependencies,
    build_configuration_manager_surface,
)
from ada_command_center.web.application.generic.layout import build_application_layout
from ada_command_center.web.application.generic.master_projection.composition import (
    compose_command_center_master_projection_backend,
)
from ada_command_center.web.application.generic.navigation import (
    create_navigation_principal_provider,
)
from ada_command_center.web.application.generic.surfaces import create_surface_router_module
from atlanticus.web.application import create_web_application
from atlanticus.web.configuration import WebEnvironment, WebSettings
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.manager import ManagerSurface
from atlanticus.web.master_projection.web import (
    MASTER_PROJECTION_INDEPENDENT_ROUTES,
    MasterMaterialReader,
    MasterProjectionWebBinding,
)
from atlanticus.web.models import (
    ApplicationMetadata,
    WebApplicationDefinition,
    WebApplicationRuntime,
)
from atlanticus.web.navigation.api import create_navigation_authorization_module
from atlanticus.web.navigation.configuration import (
    NAVIGATION_SOURCE_KEY,
    create_projected_navigation_module,
)
from atlanticus.web.storage.namespace import StorageNamespace
from atlanticus.web.users.module import create_users_module
from atlanticus.web.users.resolver import UsersAccessResolver
from atlanticus.web.users.runtime import UsersRuntime

_APPLICATION_ROOT = Path(__file__).resolve().parents[5]
_APPLICATION_DISTRIBUTION = 'ada-command-center-generic-application'
_PAGE_PACKAGE = 'ada_command_center.web.application.generic.pages'
_MANAGER_PAGE_PACKAGE = 'ada_command_center.web.application.configuration_manager.pages'


def create_application_definition(
    dependencies: ConfigurationManagerDependencies,
    *,
    identity_provider: IdentityProvider,
    users_runtime: UsersRuntime,
    master_material_reader: MasterMaterialReader | None = None,
    environment: WebEnvironment | None = None,
    namespace: StorageNamespace | None = None,
) -> WebApplicationDefinition:
    if not isinstance(dependencies, ConfigurationManagerDependencies):
        raise TypeError('Command Center dependencies are invalid')
    if not isinstance(identity_provider, IdentityProvider):
        raise TypeError('Command Center identity provider is invalid')
    if not isinstance(users_runtime, UsersRuntime):
        raise TypeError('Command Center Users runtime is invalid')
    if dependencies.administration is None:
        raise ValueError('Command Center Generic Application requires administration dependencies')
    resolved_environment = environment or WebSettings().environment
    if not isinstance(resolved_environment, WebEnvironment):
        raise TypeError('Command Center Web environment is invalid')
    if master_material_reader is not None and not isinstance(namespace, StorageNamespace):
        raise ValueError('Command Center namespace is required for Master Projection')

    manager = ManagerSurface(
        replace(build_configuration_manager_surface(dependencies), application_home_href='/')
    )
    principal_provider = create_navigation_principal_provider(
        dependencies.principal_provider,
        allow_local=resolved_environment.is_local,
    )
    navigation = create_projected_navigation_module(
        dependencies.administration.navigation_projection_store,
        source_key=NAVIGATION_SOURCE_KEY,
        principal_provider=principal_provider,
    )
    master_modules = ()
    independent_routes = ()
    if master_material_reader is not None:
        backend = compose_command_center_master_projection_backend(dependencies)
        master_modules = (
            MasterProjectionWebBinding(
                application_namespace=namespace.scope_prefix,
                environment=resolved_environment.value,
                planner=backend.planner,
                reader=master_material_reader,
                executor=backend.executor,
            ).module(),
        )
        independent_routes = MASTER_PROJECTION_INDEPENDENT_ROUTES

    application_version = version(_APPLICATION_DISTRIBUTION)
    resolver = UsersAccessResolver(
        store=dependencies.administration.users_runtime_store,
        runtime=users_runtime,
    )
    return WebApplicationDefinition(
        import_name='ada_command_center.web.application.generic',
        metadata=ApplicationMetadata(
            application_id='ada-command-center-generic-application',
            display_name='ADA Command Center',
            version=application_version,
        ),
        publications_root=_resolve_publications_root(),
        layout=partial(build_application_layout, manager=manager),
        modules=(
            *master_modules,
            create_identity_module(
                identity_provider,
                access_resolver=resolver,
                independent_routes=independent_routes,
            ),
            create_users_module(users_runtime),
            navigation,
            create_navigation_authorization_module(),
            *manager.web_modules,
            create_surface_router_module(route_prefix=MANAGER_ROUTE_PREFIX),
        ),
        page_packages=(_PAGE_PACKAGE, _MANAGER_PAGE_PACKAGE),
    )


def create_application(
    dependencies: ConfigurationManagerDependencies,
    *,
    identity_provider: IdentityProvider,
    users_runtime: UsersRuntime,
    master_material_reader: MasterMaterialReader | None = None,
    environment: WebEnvironment | None = None,
    namespace: StorageNamespace | None = None,
) -> WebApplicationRuntime:
    return create_web_application(
        create_application_definition(
            dependencies,
            identity_provider=identity_provider,
            users_runtime=users_runtime,
            master_material_reader=master_material_reader,
            environment=environment,
            namespace=namespace,
        )
    )


def _resolve_publications_root() -> Path:
    configured = os.getenv('APPLICATION_PUBLICATIONS_ROOT')
    if configured is None or not configured.strip():
        return _APPLICATION_ROOT / '.runtime' / 'publications'
    return Path(configured).expanduser().resolve()
