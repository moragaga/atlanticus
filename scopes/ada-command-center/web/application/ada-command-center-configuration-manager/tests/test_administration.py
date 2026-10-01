from pathlib import Path

from ada_command_center.web.application.configuration_manager import (
    NAVIGATION_MANAGER_ACCESS_KEY,
    NAVIGATION_SOURCE_KEY,
    PROFILES_MANAGER_ACCESS_KEY,
    USERS_MANAGER_ACCESS_KEY,
    CommandCenterAdministrationStores,
    compose_command_center_administration,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    InProcessProjectionStore,
    InProcessUsersAdministrationStore,
    InProcessUsersRegistryStore,
)
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.navigation.configuration import NavigationConfigurationCatalog
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


def test_administration_composes_generic_users_profiles_and_navigation(tmp_path: Path) -> None:
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        profile_keys=('local',),
        access_keys=(),
        administrative_override=True,
        is_local=True,
    )
    administration = compose_command_center_administration(
        stores=CommandCenterAdministrationStores(
            profiles_source=source,
            navigation_source=source,
            profiles=InProcessProjectionStore[ProfileCatalog](),
            navigation=InProcessProjectionStore[NavigationConfigurationCatalog](),
            users_registry=InProcessUsersRegistryStore(),
            users_promoted=InProcessUsersAdministrationStore(),
        ),
        principal_provider=lambda: principal,
        source_name='Local Source',
        projection_name='In-process Projection',
    )

    assert administration.users_entry.key == 'users'
    assert administration.users_entry.access_key == USERS_MANAGER_ACCESS_KEY
    assert administration.profiles_module.key == 'profiles'
    assert administration.profiles_module.access_key == PROFILES_MANAGER_ACCESS_KEY
    assert administration.navigation_module.key == 'navigation'
    assert administration.navigation_module.access_key == NAVIGATION_MANAGER_ACCESS_KEY
    assert administration.navigation_module.source_key == NAVIGATION_SOURCE_KEY
