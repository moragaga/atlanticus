from ada_command_center.web.application.configuration_manager.dependencies import (
    CommandCenterAdministrationDependencies,
    ConfigurationManagerDependencies,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    InProcessUsersRuntimeStore,
)
from ada_command_center.web.application.generic import application
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.manager import (
    ManagerEntry,
    ManagerModuleGroup,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.users.runtime import UsersRuntime


class ProjectionStoreStub:
    def get_active(self, _source_key):
        return None


class StoreStub:
    pass


def _dependencies() -> ConfigurationManagerDependencies:
    principal = ManagerPrincipal(
        subject_id='local:jane-doe',
        display_name='Jane Doe',
        profile_keys=('local',),
        administrative_override=True,
        is_local=True,
    )
    administration = CommandCenterAdministrationDependencies(
        profiles_module=None,
        navigation_module=None,
        users_entry=None,
        profiles_projection_store=ProjectionStoreStub(),
        navigation_projection_store=ProjectionStoreStub(),
        users_runtime_store=InProcessUsersRuntimeStore(),
    )
    return ConfigurationManagerDependencies(
        source_store=StoreStub(),
        projection_store=ProjectionStoreStub(),
        principal_provider=lambda: principal,
        administration=administration,
    )


def _manager_surface_definition(
    dependencies: ConfigurationManagerDependencies,
) -> ManagerSurfaceDefinition:
    return ManagerSurfaceDefinition(
        principal_provider=dependencies.principal_provider,
        groups=(ManagerModuleGroup(key='test', title='Test', order=0),),
        modules=(),
        entries=(
            ManagerEntry(
                key='test',
                group_key='test',
                title='Test',
                route='/test',
                order=0,
                layout=lambda _services: None,
            ),
        ),
        route_prefix='/manager',
    )


def test_definition_composes_identity_users_navigation_manager_and_pages(monkeypatch) -> None:
    dependencies = _dependencies()
    monkeypatch.setattr(application, 'version', lambda _distribution: '0.1.0')
    monkeypatch.setattr(
        application,
        'build_configuration_manager_surface',
        lambda _dependencies: _manager_surface_definition(dependencies),
    )

    definition = application.create_application_definition(
        dependencies,
        identity_provider=LocalIdentityProvider(subject_id='local:jane-doe'),
        users_runtime=UsersRuntime(),
    )

    assert definition.metadata.application_id == 'ada-command-center-generic-application'
    assert definition.metadata.display_name == 'ADA Command Center'
    assert definition.metadata.version == '0.1.0'
    assert definition.page_packages == (
        'ada_command_center.web.application.generic.pages',
        'ada_command_center.web.application.configuration_manager.pages',
    )
    assert tuple(module.name for module in definition.modules) == (
        'identity',
        'users',
        'navigation',
        'navigation-authorization',
        'manager-surface',
        'ada-command-center-surface-router',
    )
