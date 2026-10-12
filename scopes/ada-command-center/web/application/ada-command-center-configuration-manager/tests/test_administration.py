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
    InProcessToolMembershipStore,
    InProcessUsersRegistryStore,
    InProcessUsersRuntimeStore,
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
    runtime = InProcessUsersRuntimeStore()
    administration = compose_command_center_administration(
        stores=CommandCenterAdministrationStores(
            profiles_source=source,
            navigation_source=source,
            profiles=InProcessProjectionStore[ProfileCatalog](),
            navigation=InProcessProjectionStore[NavigationConfigurationCatalog](),
            users_registry=InProcessUsersRegistryStore(),
            users_memberships=InProcessToolMembershipStore(),
            users_runtime=runtime,
        ),
        principal_provider=lambda: principal,
        source_name='Local Source',
        projection_name='In-process Projection',
    )

    assert administration.users_entry.key == 'users'
    assert administration.users_entry.route == '/users'
    assert administration.users_entry.access_key == USERS_MANAGER_ACCESS_KEY
    assert administration.profiles_module.key == 'profiles'
    assert administration.profiles_module.route == '/profiles'
    assert administration.profiles_module.access_key == PROFILES_MANAGER_ACCESS_KEY
    assert administration.navigation_module.key == 'navigation'
    assert administration.navigation_module.route == '/navigation'
    assert administration.navigation_module.access_key == NAVIGATION_MANAGER_ACCESS_KEY
    assert administration.navigation_module.source_key == NAVIGATION_SOURCE_KEY
    assert administration.users_runtime_store is runtime
    assert administration.users_reconstruction_entry is not None
    assert administration.users_reconstruction_entry.route == '/users-reconstruction'


def test_command_center_runtime_base_publication_preserves_domain_extensions():
    from dataclasses import replace

    from atlanticus.web.profiles.models import BASIC_PROFILE
    from atlanticus.web.users.identity import build_user_key
    from atlanticus.web.users.models import (
        RuntimeOperational,
        RuntimeOperationalReference,
        RuntimeProfile,
        RuntimeUser,
        UserIdentity,
    )

    identity = UserIdentity(
        user_id=build_user_key(issuer='test', subject_id='alice'),
        issuer='test',
        subject_id='alice',
        display_name='Alice',
    )
    operational = RuntimeOperational(area=RuntimeOperationalReference(id='area', label='Area'))
    store = InProcessUsersRuntimeStore()
    user = RuntimeUser(
        identity=identity,
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
        access_keys=('users.view',),
        operational=operational,
    )
    store.upsert_base_user(user)
    changed = store.upsert_base_user(
        replace(user, enabled=False, operational=RuntimeOperational(), access_keys=())
    )
    assert changed.enabled is False
    assert changed.access_keys == ('users.view',)
    assert changed.operational == operational
