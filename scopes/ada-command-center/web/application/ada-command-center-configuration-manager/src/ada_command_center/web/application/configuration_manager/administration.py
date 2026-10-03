from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ada_command_center.web.application.configuration_manager.dependencies import (
    CommandCenterAdministrationDependencies,
)
from atlanticus.web.compositions.navigation_manager import compose_navigation_manager
from atlanticus.web.compositions.profiles_manager import (
    PROFILES_CONFIGURATION_SOURCE_KEY,
    compose_profiles_manager,
)
from atlanticus.web.compositions.users_manager import (
    compose_users_manager,
    compose_users_projection_manager,
)
from atlanticus.web.manager import ManagerPrincipalProvider
from atlanticus.web.navigation.configuration import (
    NAVIGATION_SOURCE_KEY,
    NavigationConfigurationCatalog,
    NavigationProfileOption,
)
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.recovery import ToolUsersRecoveryService, ToolUsersRecoverySnapshot
from atlanticus.web.users.store import (
    ToolMembershipStore,
    UsersDirectoryReader,
    UsersRegistryStore,
    UsersRuntimeStore,
)

USERS_MANAGER_ACCESS_KEY = 'users.manage'
PROFILES_MANAGER_ACCESS_KEY = 'profiles.manage'
NAVIGATION_MANAGER_ACCESS_KEY = 'navigation.manage'


@dataclass(frozen=True, slots=True)
class CommandCenterAdministrationStores:
    profiles_source: SourceStore
    navigation_source: SourceStore
    profiles: ProjectionStore[ProfileCatalog]
    navigation: ProjectionStore[NavigationConfigurationCatalog]
    users_registry: UsersRegistryStore
    users_memberships: ToolMembershipStore
    users_runtime: UsersRuntimeStore
    users_directory: UsersDirectoryReader | None = None
    users_recovery: ToolUsersRecoveryService | Callable[[], ToolUsersRecoveryService] | None = None
    users_snapshot_ids: Callable[[], tuple[str, ...]] | None = None
    users_snapshot_summaries: Callable[[], tuple[tuple[str, str | None], ...]] | None = None
    users_read_snapshot: Callable[[str], ToolUsersRecoverySnapshot] | None = None

    def __post_init__(self) -> None:
        for name, expected in (
            ('profiles_source', SourceStore),
            ('navigation_source', SourceStore),
            ('profiles', ProjectionStore),
            ('navigation', ProjectionStore),
            ('users_registry', UsersRegistryStore),
            ('users_memberships', ToolMembershipStore),
            ('users_runtime', UsersRuntimeStore),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f'Command Center {name} must implement {expected.__name__}')
        if self.users_directory is not None and not isinstance(
            self.users_directory, UsersDirectoryReader
        ):
            raise TypeError('Command Center users_directory must implement UsersDirectoryReader')
        if (self.users_recovery is None) != (self.users_snapshot_ids is None):
            raise ValueError('Users recovery and snapshot catalog must be injected together')
        if (
            self.users_recovery is not None
            and not isinstance(self.users_recovery, ToolUsersRecoveryService)
            and not callable(self.users_recovery)
        ):
            raise TypeError('Command Center users recovery service has an invalid type')


def compose_command_center_administration(
    *,
    stores: CommandCenterAdministrationStores,
    principal_provider: ManagerPrincipalProvider,
    source_name: str = 'Source',
    projection_name: str = 'Projection',
) -> CommandCenterAdministrationDependencies:
    if not isinstance(stores, CommandCenterAdministrationStores):
        raise TypeError('Command Center administration stores are invalid')
    if not callable(principal_provider):
        raise TypeError('Command Center principal provider must be callable')

    profiles = compose_profiles_manager(
        source_store=stores.profiles_source,
        projection_store=stores.profiles,
        principal_provider=principal_provider,
        group_key='configuration',
        title='Perfiles',
        description='Define los perfiles disponibles para ADA Command Center.',
        source_name=source_name,
        projection_name=projection_name,
        access_key=PROFILES_MANAGER_ACCESS_KEY,
    )

    def profiles_provider() -> ProfileCatalog:
        active = stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY)
        if active is None:
            return ProfileCatalog()
        if active.source_key != PROFILES_CONFIGURATION_SOURCE_KEY:
            raise ValueError('Profiles projection source key does not match request')
        if not isinstance(active.payload, ProfileCatalog):
            raise TypeError('Profiles projection payload has an invalid type')
        return active.payload

    def navigation_profile_options() -> tuple[NavigationProfileOption, ...]:
        return tuple(
            NavigationProfileOption(profile.key, profile.label)
            for profile in profiles_provider().all()
            if profile.key not in {'root', 'local'}
        )

    navigation = compose_navigation_manager(
        source_store=stores.navigation_source,
        projection_store=stores.navigation,
        principal_provider=principal_provider,
        group_key='configuration',
        title='Navegación',
        description='Define las rutas y perfiles visibles en ADA Command Center.',
        source_key=NAVIGATION_SOURCE_KEY,
        source_name=source_name,
        projection_name=projection_name,
        access_key=NAVIGATION_MANAGER_ACCESS_KEY,
        profile_options_provider=navigation_profile_options,
    )
    users_administration = UsersAdministrationService(
        registry=stores.users_registry,
        memberships=stores.users_memberships,
        profiles=profiles_provider,
        directory=stores.users_directory,
    )
    users = compose_users_manager(
        administration=users_administration,
        principal_provider=principal_provider,
        group_key='administration',
        title='Usuarios',
        access_key=USERS_MANAGER_ACCESS_KEY,
    )
    users_projection = (
        compose_users_projection_manager(
            recovery=stores.users_recovery,
            snapshot_ids=stores.users_snapshot_ids,
            snapshot_summaries=stores.users_snapshot_summaries,
            read_snapshot=stores.users_read_snapshot,
            principal_provider=principal_provider,
            group_key='administration',
            access_key=USERS_MANAGER_ACCESS_KEY,
        )
        if stores.users_recovery is not None and stores.users_snapshot_ids is not None
        else None
    )
    return CommandCenterAdministrationDependencies(
        profiles_module=profiles.module,
        navigation_module=navigation.module,
        users_entry=users.entry,
        profiles_projection_store=stores.profiles,
        navigation_projection_store=stores.navigation,
        users_runtime_store=stores.users_runtime,
        users_projection_entry=users_projection,
        users_recovery=stores.users_recovery,
        users_snapshot_ids=stores.users_snapshot_ids,
    )
