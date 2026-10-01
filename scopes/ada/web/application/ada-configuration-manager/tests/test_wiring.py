from __future__ import annotations

import pytest

from ada.web.application.configuration_manager.composition import (
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.local_runtime import (
    InProcessProjectionStore,
    create_local_configuration_manager_dependencies,
    create_local_configuration_manager_stores,
)
from ada.web.application.configuration_manager.wiring import (
    NAVIGATION_SOURCE_KEY,
    TOOLS_SOURCE_KEY,
    compose_configuration_manager_dependencies,
    read_manager_projection,
)
from atlanticus.web.compositions.navigation_manager import (
    NAVIGATION_MANAGER_SOURCE_SERVICE,
    NAVIGATION_MANAGER_VALIDATION_SERVICE,
)
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.manager import ManagerPrincipal, ManagerSurface
from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationProjectionError
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.errors import ProjectionStoreError
from atlanticus.web.services import ServiceRegistry


def test_local_dependencies_use_one_injected_principal_for_manager(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    current = ManagerPrincipal('test-user', 'Test user', access_keys=())

    def provider():
        return current

    dependencies = create_local_configuration_manager_dependencies(
        source_root=tmp_path, principal_provider=provider
    )
    surface = ManagerSurface(build_configuration_manager_surface(dependencies))
    assert surface.registry.visible_items(provider(), surface.authorization) == ()

    current = ManagerPrincipal(
        'test-user',
        'Test user',
        access_keys=(),
        administrative_override=True,
    )
    visible = surface.registry.visible_items(provider(), surface.authorization)
    assert {item.key for item in visible} == {
        'users',
        'operational-identification',
        'profiles',
        'access',
        'navigation',
        'tools',
        'kpis',
        'kpi-definitions',
    }
    assert surface.registry.require_entry('users').title == 'Usuarios'
    assert surface.registry.require('operational-identification').access_key == 'operational.manage'


def test_local_factory_is_unavailable_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    with pytest.raises(RuntimeError, match='outside local environment'):
        create_local_configuration_manager_dependencies(source_root=tmp_path)


def test_projection_transport_failure_is_normalized_without_leaking_details():
    class Unavailable(InProcessProjectionStore):
        def get_active(self, _source_key):
            try:
                raise ConnectionError('sensitive-provider-detail')
            except ConnectionError as error:
                raise ProfilesConfigurationProjectionError('Projection unavailable') from error

    with pytest.raises(ProjectionStoreError, match='provider is unavailable') as caught:
        read_manager_projection(
            Unavailable(),
            PROFILES_CONFIGURATION_SOURCE_KEY,
            ProfileCatalog,
            unavailable_causes=(ConnectionError,),
        )
    assert 'sensitive-provider-detail' not in str(caught.value)


def test_invalid_projection_is_not_misreported_as_provider_outage():
    class Invalid(InProcessProjectionStore):
        def get_active(self, _source_key):
            raise ProfilesConfigurationProjectionError('Invalid document')

    with pytest.raises(ProfilesConfigurationProjectionError, match='Invalid document'):
        read_manager_projection(Invalid(), PROFILES_CONFIGURATION_SOURCE_KEY, ProfileCatalog)


def test_manager_sources_keep_independent_application_boundaries(tmp_path):
    from ada.web.access.configuration import AdaAccessConfiguration
    from ada.web.application.configuration_manager.wiring import (
        ConfigurationManagerStores,
        compose_configuration_manager_dependencies,
    )
    from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
    from atlanticus.web.users.models import UsersRegistrySnapshot
    from atlanticus.web.users.store import UsersAdministrationStore, UsersRegistryStore

    calls = []

    class TrackingSource(LocalSourceStore):
        def __init__(self, key):
            super().__init__(LocalSourceSettings(root=tmp_path / key))
            self.key = key

        def get_current(self, source_key):
            calls.append((self.key, source_key.value))
            return super().get_current(source_key)

    class Registry(UsersRegistryStore):
        def load(self):
            return UsersRegistrySnapshot()

        def replace(self, users, *, expected_version):
            return UsersRegistrySnapshot(users=users, version='test')

    class Promoted(UsersAdministrationStore):
        def get(self, user_id):
            return None

        def list_users(self):
            return ()

        def create(self, user):
            return user

        def replace(self, user):
            return user

    source_a = TrackingSource('application')
    source_b = TrackingSource('tool')
    stores = ConfigurationManagerStores(
        navigation_source=source_a,
        tools_source=source_b,
        access_source=source_a,
        profiles_source=source_a,
        kpi_registry_source=source_b,
        kpi_definitions_source=source_b,
        navigation=InProcessProjectionStore(),
        tools=InProcessProjectionStore(),
        access=InProcessProjectionStore[AdaAccessConfiguration](),
        profiles=InProcessProjectionStore[ProfileCatalog](),
        kpi_registry=InProcessProjectionStore(),
        kpi_definitions=InProcessProjectionStore(),
        users_registry=Registry(),
        users_promoted=Promoted(),
    )
    deps = compose_configuration_manager_dependencies(
        stores=stores,
        principal_provider=lambda: ManagerPrincipal('subject', 'Subject', access_keys=()),
    )
    assert deps.navigation_projection_store is stores.navigation
    services = ServiceRegistry()
    assert deps.navigation_module.web_module is not None
    assert deps.navigation_module.web_module.register_services is not None
    deps.navigation_module.web_module.register_services(services)
    services.require(NAVIGATION_MANAGER_SOURCE_SERVICE).get_source_snapshot()
    deps.tools_source.get_current()
    deps.access_source.get_current()
    assert calls == [
        ('application', 'navigation'),
        ('tool', 'tools'),
        ('application', 'ada-access'),
    ]


def test_projection_source_mismatch_is_an_invalid_contract():
    from datetime import UTC, datetime

    from atlanticus.web.projection.models import ProjectionRecord
    from atlanticus.web.source.models import SourceKey, SourceReleaseId

    instant = datetime(2026, 9, 24, tzinfo=UTC)
    store = InProcessProjectionStore[ProfileCatalog]()
    store.replace_active(
        ProjectionRecord(
            source_key=SourceKey('unexpected'),
            source_release_id=SourceReleaseId('test-release'),
            source_published_at_utc=instant,
            projected_at_utc=instant,
            payload=ProfileCatalog(),
        )
    )

    class Mismatched(InProcessProjectionStore):
        def get_active(self, _source_key):
            return store.get_active(SourceKey('unexpected'))

    with pytest.raises(ValueError, match='source key does not match'):
        read_manager_projection(Mismatched(), PROFILES_CONFIGURATION_SOURCE_KEY, ProfileCatalog)


def test_local_stores_are_explicitly_scoped_to_development(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path)
    assert stores.navigation_source.get_current(NAVIGATION_SOURCE_KEY).current is None
    assert stores.tools_source.get_current(TOOLS_SOURCE_KEY).current is None
    assert stores.users_registry.load().users == ()


def test_navigation_manager_uses_projected_profiles_for_validation(tmp_path) -> None:
    from datetime import UTC, datetime

    from atlanticus.web.navigation.configuration import (
        NavigationConfigurationCatalog,
        NavigationLinkConfiguration,
    )
    from atlanticus.web.profiles.models import ProfileDefinition
    from atlanticus.web.projection.models import ProjectionRecord
    from atlanticus.web.source.models import SourceReleaseId

    stores = create_local_configuration_manager_stores(source_root=tmp_path)
    instant = datetime(2026, 10, 1, 12, tzinfo=UTC)
    stores.profiles.replace_active(
        ProjectionRecord(
            source_key=PROFILES_CONFIGURATION_SOURCE_KEY,
            source_release_id=SourceReleaseId('profiles-1'),
            source_published_at_utc=instant,
            projected_at_utc=instant,
            payload=ProfileCatalog(
                profiles=(
                    ProfileDefinition(
                        key='operator',
                        label='Operator',
                        background_color='#123456',
                    ),
                )
            ),
        )
    )
    dependencies = compose_configuration_manager_dependencies(
        stores=stores,
        principal_provider=lambda: ManagerPrincipal(
            'subject',
            'Subject',
            administrative_override=True,
        ),
    )
    services = ServiceRegistry()
    assert dependencies.navigation_module.web_module is not None
    assert dependencies.navigation_module.web_module.register_services is not None
    dependencies.navigation_module.web_module.register_services(services)
    validation = services.require(NAVIGATION_MANAGER_VALIDATION_SERVICE)

    valid = NavigationConfigurationCatalog(
        links=(
            NavigationLinkConfiguration(
                key='home',
                label='Inicio',
                href='/',
                allowed_profiles=('operator',),
            ),
        )
    )
    invalid = NavigationConfigurationCatalog(
        links=(
            NavigationLinkConfiguration(
                key='home',
                label='Inicio',
                href='/',
                allowed_profiles=('unknown',),
            ),
        )
    )

    assert validation.validate_draft(valid.to_document()).valid is True
    rejected = validation.validate_draft(invalid.to_document())
    assert rejected.valid is False
    assert rejected.issues[0].code == 'navigation.profile.unknown'
