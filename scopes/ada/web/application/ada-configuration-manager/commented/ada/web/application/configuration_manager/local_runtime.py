from __future__ import annotations

# Construye infraestructura temporal exclusivamente para pruebas locales.
# La composición productiva debe inyectar proveedores durables explícitos.

import os
from collections.abc import Callable
from pathlib import Path
from typing import Generic, TypeVar

from ada.web.access.configuration import AdaAccessConfiguration
from ada.web.application.configuration_manager.application import (
    create_configuration_manager_application,
)
from ada.web.application.configuration_manager.dependencies import ConfigurationManagerDependencies
from ada.web.application.configuration_manager.wiring import (
    ADA_ACCESS_SOURCE_KEY,
    KPI_DEFINITION_SOURCE_KEY,
    KPI_REGISTRY_SOURCE_KEY,
    MANAGER_ACCESS_KEYS,
    NAVIGATION_SOURCE_KEY,
    TOOLS_SOURCE_KEY,
    ConfigurationManagerStores,
    compose_configuration_manager_dependencies,
)
from ada.web.kpis.definition.projection.local import (
    LocalKpiDefinitionProjectionStore,
    LocalKpiDefinitionProjectionStoreSettings,
)
from ada.web.kpis.registry.projection.local import (
    LocalKpiRegistryProjectionStore,
    LocalKpiRegistryProjectionStoreSettings,
)
from ada.web.tools.configuration import ToolConfiguration
from atlanticus.web.configuration import WebSettings
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.models import WebApplicationRuntime
from atlanticus.web.navigation.configuration import NavigationConfigurationCatalog
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import SourceKey
from atlanticus.web.users.errors import UserAlreadyPromotedError, UsersRegistryConflictError
from atlanticus.web.users.models import UserRecord, UsersRegistrySnapshot
from atlanticus.web.users.store import UsersAdministrationStore, UsersRegistryStore

__all__ = [
    'ADA_ACCESS_SOURCE_KEY',
    'KPI_DEFINITION_SOURCE_KEY',
    'KPI_REGISTRY_SOURCE_KEY',
    'NAVIGATION_SOURCE_KEY',
    'TOOLS_SOURCE_KEY',
    'InProcessProjectionStore',
    'InProcessUsersRegistryStore',
    'InProcessUsersAdministrationStore',
    'create_local_configuration_manager_application',
    'create_local_configuration_manager_stores',
    'create_local_configuration_manager_dependencies',
]

PayloadT = TypeVar('PayloadT')


# Contrato de estado de la frontera.
class InProcessProjectionStore(ProjectionStore[PayloadT], Generic[PayloadT]):
    # Verifica invariantes y deriva datos de la entrada explícita.
    def __init__(self) -> None:
        self._active: dict[SourceKey, ProjectionRecord[PayloadT]] = {}

    # Verifica invariantes y deriva datos de la entrada explícita.
    def get_active(self, source_key: SourceKey) -> ProjectionRecord[PayloadT] | None:
        return self._active.get(source_key)

    # Verifica invariantes y deriva datos de la entrada explícita.
    def replace_active(self, projection: ProjectionRecord[PayloadT]) -> ProjectionRecord[PayloadT]:
        self._active[projection.source_key] = projection
        return projection


# Contrato de estado de la frontera.
class InProcessUsersRegistryStore(UsersRegistryStore):
    # Verifica invariantes y deriva datos de la entrada explícita.
    def __init__(self) -> None:
        self._snapshot = UsersRegistrySnapshot()
        self._revision = 0

    # Verifica invariantes y deriva datos de la entrada explícita.
    def load(self) -> UsersRegistrySnapshot:
        return self._snapshot

    # Verifica invariantes y deriva datos de la entrada explícita.
    def replace(
        self, users: tuple[UserRecord, ...], *, expected_version: str | None
    ) -> UsersRegistrySnapshot:
        if self._snapshot.version != expected_version:
            raise UsersRegistryConflictError('Users registry changed concurrently')
        self._revision += 1
        self._snapshot = UsersRegistrySnapshot(users=users, version=f'local-{self._revision}')
        return self._snapshot


# Contrato de estado de la frontera.
class InProcessUsersAdministrationStore(UsersAdministrationStore):
    # Verifica invariantes y deriva datos de la entrada explícita.
    def __init__(self) -> None:
        self._users: dict[str, UserRecord] = {}

    # Verifica invariantes y deriva datos de la entrada explícita.
    def get(self, user_id: str) -> UserRecord | None:
        return self._users.get(user_id)

    # Verifica invariantes y deriva datos de la entrada explícita.
    def list_users(self) -> tuple[UserRecord, ...]:
        return tuple(sorted(self._users.values(), key=lambda user: user.user_id))

    # Verifica invariantes y deriva datos de la entrada explícita.
    def create(self, user: UserRecord) -> UserRecord:
        if user.user_id in self._users:
            raise UserAlreadyPromotedError('User is already promoted')
        self._users[user.user_id] = user
        return user

    # Verifica invariantes y deriva datos de la entrada explícita.
    def replace(self, user: UserRecord) -> UserRecord:
        if user.user_id not in self._users:
            raise ValueError('Promoted user does not exist')
        self._users[user.user_id] = user
        return user


# Composición o lectura independiente del proveedor físico.
def create_local_configuration_manager_stores(
    *, source_root: Path | None = None
) -> ConfigurationManagerStores:
    if not WebSettings().environment.is_local:
        raise RuntimeError(
            'Local Configuration Manager is unavailable outside local environment'
        )
    root = source_root or _source_root()
    source_store = LocalSourceStore(LocalSourceSettings(root=root))
    projection_root = root.parent / f'{root.name}-projection'
    stores = ConfigurationManagerStores(
        navigation_source=source_store,
        tools_source=source_store,
        access_source=source_store,
        profiles_source=source_store,
        kpi_registry_source=source_store,
        kpi_definitions_source=source_store,
        navigation=InProcessProjectionStore[NavigationConfigurationCatalog](),
        tools=InProcessProjectionStore[ToolConfiguration](),
        access=InProcessProjectionStore[AdaAccessConfiguration](),
        profiles=InProcessProjectionStore[ProfileCatalog](),
        kpi_registry=LocalKpiRegistryProjectionStore(
            LocalKpiRegistryProjectionStoreSettings(root=projection_root)
        ),
        kpi_definitions=LocalKpiDefinitionProjectionStore(
            LocalKpiDefinitionProjectionStoreSettings(root=projection_root)
        ),
        users_registry=InProcessUsersRegistryStore(),
        users_promoted=InProcessUsersAdministrationStore(),
    )
    return stores


# Composición o lectura independiente del proveedor físico.
def create_local_configuration_manager_dependencies(
    *,
    source_root: Path | None = None,
    principal_provider: Callable[[], ManagerPrincipal] | None = None,
) -> ConfigurationManagerDependencies:
    stores = create_local_configuration_manager_stores(source_root=source_root)
    if principal_provider is None:
        local_principal = ManagerPrincipal(
            subject_id='local',
            display_name='Administrador local',
            access_keys=MANAGER_ACCESS_KEYS,
            is_local=True,
        )
        principal_provider = lambda: local_principal
    return compose_configuration_manager_dependencies(
        stores=stores,
        principal_provider=principal_provider,
        source_name='Local Source',
        projection_name='In-process Projection',
        profiles_projection_name='In-process Projection',
        kpi_projection_name='Local Projection',
    )


# Composición o lectura independiente del proveedor físico.
def create_local_configuration_manager_application(
    *, source_root: Path | None = None
) -> WebApplicationRuntime:
    return create_configuration_manager_application(
        create_local_configuration_manager_dependencies(source_root=source_root)
    )


# Composición o lectura independiente del proveedor físico.
def _source_root() -> Path:
    configured = os.getenv('ADA_CONFIGURATION_MANAGER_SOURCE_ROOT')
    if configured is not None and configured.strip():
        return Path(configured).expanduser().resolve()
    return Path.cwd() / '.runtime' / 'configuration-manager' / 'source'
