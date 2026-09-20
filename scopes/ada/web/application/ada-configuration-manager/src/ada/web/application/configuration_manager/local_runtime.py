from __future__ import annotations

import os
from pathlib import Path
from typing import Generic, TypeVar

from ada.web.access.configuration import (
    AdaAccessConfiguration,
    AdaAccessSourceService,
    create_ada_access_projection_service,
)
from ada.web.application.configuration_manager.access import ACCESS_MANAGER_ACCESS_KEY
from ada.web.application.configuration_manager.application import (
    create_configuration_manager_application,
)
from ada.web.application.configuration_manager.composition import (
    KPI_MANAGER_ACCESS_KEY,
    NAVIGATION_MANAGER_ACCESS_KEY,
    PROFILES_MANAGER_ACCESS_KEY,
    TOOLS_MANAGER_ACCESS_KEY,
    USERS_MANAGER_ACCESS_KEY,
)
from ada.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from ada.web.application.configuration_manager.tool_kpi_destinations import (
    ToolConfigurationKpiDestinationCatalogProvider,
)
from ada.web.kpis.configuration import (
    KpiConfiguration,
    KpiSourceService,
    create_kpi_projection_service,
)
from ada.web.kpis.definition import (
    KpiDefinitionCatalog,
    KpiDefinitionSourceService,
    create_kpi_definition_projection_service,
)
from ada.web.tools.configuration import (
    ToolConfiguration,
    ToolSourceService,
    create_tool_projection_service,
)
from atlanticus.web.compositions.profiles_manager import (
    PROFILES_CONFIGURATION_SOURCE_KEY,
    compose_profiles_manager,
)
from atlanticus.web.compositions.users_manager import compose_users_manager
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.models import WebApplicationRuntime
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationSourceService,
    create_navigation_projection_service,
)
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import SourceKey
from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.errors import UserAlreadyPromotedError, UsersRegistryConflictError
from atlanticus.web.users.models import UserRecord, UsersRegistrySnapshot
from atlanticus.web.users.store import UsersAdministrationStore, UsersRegistryStore

PayloadT = TypeVar('PayloadT')

NAVIGATION_SOURCE_KEY = SourceKey('navigation')
TOOLS_SOURCE_KEY = SourceKey('tools')
KPI_SOURCE_KEY = SourceKey('kpis')
KPI_DEFINITION_SOURCE_KEY = SourceKey('kpi-definitions')
ADA_ACCESS_SOURCE_KEY = SourceKey('ada-access')


class InProcessProjectionStore(ProjectionStore[PayloadT], Generic[PayloadT]):
    def __init__(self) -> None:
        self._active: dict[SourceKey, ProjectionRecord[PayloadT]] = {}

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[PayloadT] | None:
        return self._active.get(source_key)

    def replace_active(
        self,
        projection: ProjectionRecord[PayloadT],
    ) -> ProjectionRecord[PayloadT]:
        self._active[projection.source_key] = projection
        return projection


class InProcessUsersRegistryStore(UsersRegistryStore):
    def __init__(self) -> None:
        self._snapshot = UsersRegistrySnapshot()
        self._revision = 0

    def load(self) -> UsersRegistrySnapshot:
        return self._snapshot

    def replace(
        self,
        users: tuple[UserRecord, ...],
        *,
        expected_version: str | None,
    ) -> UsersRegistrySnapshot:
        if self._snapshot.version != expected_version:
            raise UsersRegistryConflictError('Users registry changed concurrently')
        self._revision += 1
        self._snapshot = UsersRegistrySnapshot(
            users=users,
            version=f'local-{self._revision}',
        )
        return self._snapshot


class InProcessUsersAdministrationStore(UsersAdministrationStore):
    def __init__(self) -> None:
        self._users: dict[str, UserRecord] = {}

    def get(self, user_id: str) -> UserRecord | None:
        return self._users.get(user_id)

    def list_users(self) -> tuple[UserRecord, ...]:
        return tuple(sorted(self._users.values(), key=lambda user: user.user_id))

    def create(self, user: UserRecord) -> UserRecord:
        if user.user_id in self._users:
            raise UserAlreadyPromotedError('User is already promoted')
        self._users[user.user_id] = user
        return user

    def replace(self, user: UserRecord) -> UserRecord:
        if user.user_id not in self._users:
            raise ValueError('Promoted user does not exist')
        self._users[user.user_id] = user
        return user


def create_local_configuration_manager_dependencies(
    *,
    source_root: Path | None = None,
) -> ConfigurationManagerDependencies:
    root = source_root or _source_root()
    source_store = LocalSourceStore(LocalSourceSettings(root=root))

    navigation_projection_store = InProcessProjectionStore[NavigationConfigurationCatalog]()
    tools_projection_store = InProcessProjectionStore[ToolConfiguration]()
    kpi_projection_store = InProcessProjectionStore[KpiConfiguration]()
    kpi_definition_projection_store = InProcessProjectionStore[KpiDefinitionCatalog]()
    profiles_projection_store = InProcessProjectionStore[ProfileCatalog]()
    access_projection_store = InProcessProjectionStore[AdaAccessConfiguration]()

    navigation_source = NavigationSourceService(
        source=source_store,
        source_key=NAVIGATION_SOURCE_KEY,
    )
    tools_source = ToolSourceService(source=source_store, source_key=TOOLS_SOURCE_KEY)
    kpis_source = KpiSourceService(source=source_store, source_key=KPI_SOURCE_KEY)
    kpi_definitions_source = KpiDefinitionSourceService(
        source=source_store,
        source_key=KPI_DEFINITION_SOURCE_KEY,
    )
    access_source = AdaAccessSourceService(
        source=source_store,
        source_key=ADA_ACCESS_SOURCE_KEY,
    )

    navigation_projection = create_navigation_projection_service(
        source=source_store,
        projection=navigation_projection_store,
    )
    tools_projection = create_tool_projection_service(
        source=source_store,
        projection=tools_projection_store,
    )
    kpi_destinations = ToolConfigurationKpiDestinationCatalogProvider(
        projection=tools_projection_store,
        source_key=TOOLS_SOURCE_KEY,
    )
    kpis_projection = create_kpi_projection_service(
        source=source_store,
        projection=kpi_projection_store,
        destinations=kpi_destinations,
    )
    kpi_definitions_projection = create_kpi_definition_projection_service(
        source=source_store,
        projection=kpi_definition_projection_store,
        kpi_configuration_projection=kpi_projection_store,
        kpi_configuration_source_key=KPI_SOURCE_KEY,
    )
    access_projection = create_ada_access_projection_service(
        source=source_store,
        projection=access_projection_store,
        profiles_projection=profiles_projection_store,
        profiles_source_key=PROFILES_CONFIGURATION_SOURCE_KEY,
    )

    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        access_keys=(
            USERS_MANAGER_ACCESS_KEY,
            PROFILES_MANAGER_ACCESS_KEY,
            ACCESS_MANAGER_ACCESS_KEY,
            NAVIGATION_MANAGER_ACCESS_KEY,
            TOOLS_MANAGER_ACCESS_KEY,
            KPI_MANAGER_ACCESS_KEY,
        ),
        is_local=True,
    )
    profiles_manager = compose_profiles_manager(
        source_store=source_store,
        projection_store=profiles_projection_store,
        principal_provider=lambda: principal,
        group_key='configuration',
        title='Perfiles',
        description=(
            'Define los perfiles disponibles y su presentación visual dentro del sistema.'
        ),
        source_name='Local Source',
        projection_name='In-process Projection',
        access_key=PROFILES_MANAGER_ACCESS_KEY,
    )

    def profiles_provider() -> ProfileCatalog:
        active = profiles_projection_store.get_active(PROFILES_CONFIGURATION_SOURCE_KEY)
        return active.payload if active is not None else ProfileCatalog()

    users_administration = UsersAdministrationService(
        registry=InProcessUsersRegistryStore(),
        promoted=InProcessUsersAdministrationStore(),
        profiles=profiles_provider,
    )
    users_manager = compose_users_manager(
        administration=users_administration,
        principal_provider=lambda: principal,
        group_key='administration',
        access_key=USERS_MANAGER_ACCESS_KEY,
    )
    return ConfigurationManagerDependencies(
        navigation_source=navigation_source,
        navigation_projection=navigation_projection,
        tools_source=tools_source,
        tools_projection=tools_projection,
        access_source=access_source,
        access_projection=access_projection,
        profiles_projection=profiles_projection_store,
        principal_provider=lambda: principal,
        profiles_module=profiles_manager.module,
        users_entry=users_manager.entry,
        kpis_source=kpis_source,
        kpis_projection=kpis_projection,
        kpi_destinations=kpi_destinations,
        kpi_configuration_projection=kpi_projection_store,
        kpi_definitions_source=kpi_definitions_source,
        kpi_definitions_projection=kpi_definitions_projection,
        navigation_source_name='Local Source',
        navigation_projection_name='In-process Projection',
        tools_source_name='Local Source',
        tools_projection_name='In-process Projection',
        access_source_name='Local Source',
        access_projection_name='In-process Projection',
        kpis_source_name='Local Source',
        kpis_projection_name='In-process Projection',
        kpi_definitions_source_name='Local Source',
        kpi_definitions_projection_name='In-process Projection',
    )


def create_local_configuration_manager_application(
    *,
    source_root: Path | None = None,
) -> WebApplicationRuntime:
    return create_configuration_manager_application(
        create_local_configuration_manager_dependencies(source_root=source_root)
    )


def _source_root() -> Path:
    configured = os.getenv('ADA_CONFIGURATION_MANAGER_SOURCE_ROOT')
    if configured is not None and configured.strip():
        return Path(configured).expanduser().resolve()
    return Path.cwd() / '.runtime' / 'configuration-manager' / 'source'
