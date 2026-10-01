from __future__ import annotations

from dataclasses import dataclass

from ada_command_center.web.application.configuration_manager.dependencies import (
    CommandCenterAdministrationDependencies,
)
from atlanticus.web.compositions.navigation_manager import compose_navigation_manager
from atlanticus.web.compositions.profiles_manager import (
    PROFILES_CONFIGURATION_SOURCE_KEY,
    compose_profiles_manager,
)
from atlanticus.web.compositions.users_manager import compose_users_manager
from atlanticus.web.manager import ManagerPrincipalProvider
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationProfileOption,
)
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.store import (
    UsersAdministrationStore,
    UsersDirectoryReader,
    UsersRegistryStore,
)

USERS_MANAGER_ACCESS_KEY = 'users.manage'
PROFILES_MANAGER_ACCESS_KEY = 'profiles.manage'
NAVIGATION_MANAGER_ACCESS_KEY = 'navigation.manage'
NAVIGATION_SOURCE_KEY = SourceKey('navigation')


@dataclass(frozen=True, slots=True)
class CommandCenterAdministrationStores:
    profiles_source: SourceStore
    navigation_source: SourceStore
    profiles: ProjectionStore[ProfileCatalog]
    navigation: ProjectionStore[NavigationConfigurationCatalog]
    users_registry: UsersRegistryStore
    users_promoted: UsersAdministrationStore
    users_directory: UsersDirectoryReader | None = None

    def __post_init__(self) -> None:
        for name, expected in (
            ('profiles_source', SourceStore),
            ('navigation_source', SourceStore),
            ('profiles', ProjectionStore),
            ('navigation', ProjectionStore),
            ('users_registry', UsersRegistryStore),
            ('users_promoted', UsersAdministrationStore),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f'Command Center {name} must implement {expected.__name__}')
        if self.users_directory is not None and not isinstance(
            self.users_directory, UsersDirectoryReader
        ):
            raise TypeError('Command Center users_directory must implement UsersDirectoryReader')


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
    users = compose_users_manager(
        administration=UsersAdministrationService(
            registry=stores.users_registry,
            promoted=stores.users_promoted,
            profiles=profiles_provider,
            directory=stores.users_directory,
        ),
        principal_provider=principal_provider,
        group_key='administration',
        title='Usuarios',
        access_key=USERS_MANAGER_ACCESS_KEY,
    )
    return CommandCenterAdministrationDependencies(
        profiles_module=profiles.module,
        navigation_module=navigation.module,
        users_entry=users.entry,
        profiles_projection_store=stores.profiles,
        navigation_projection_store=stores.navigation,
    )
