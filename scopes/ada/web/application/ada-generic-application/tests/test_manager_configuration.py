from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from flask import Flask

from ada.web.access.configuration import AdaAccessConfiguration
from ada.web.access.configuration.errors import AdaAccessConfigurationProjectionError
from ada.web.access.models import ProfileAccessGrant
from ada.web.application.configuration_manager.composition import (
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.local_runtime import (
    InProcessProjectionStore,
    InProcessUsersAdministrationStore,
    InProcessUsersRegistryStore,
)
from ada.web.application.configuration_manager.wiring import (
    ADA_ACCESS_SOURCE_KEY,
    MANAGER_ACCESS_KEYS,
    ConfigurationManagerStores,
)
from ada.web.application.generic import bootstrap
from ada.web.application.generic.manager_principal import (
    ManagerPrincipalBinding,
    compose_integrated_manager_dependencies,
)
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.registry.models import KpiRegistry
from atlanticus.connectivity.cosmos import CosmosOperationError
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.identity.access import (
    ACCESS_RUNTIME_SERVICE_KEY,
    AccessDecision,
    AccessRuntime,
    AccessSnapshot,
    AccessStatus,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.manager import ManagerSurface
from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationProjectionError
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.errors import ProjectionStoreError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import SourceKey, SourceReleaseId
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.runtime import UsersRuntime


def _access(subject: str, *, issuer: str = 'atlanticus-local', provider: str = 'local'):
    return AccessSnapshot.resolved(
        load_id='load-1',
        identity=AuthenticatedIdentity(provider_key=provider, issuer=issuer, subject_id=subject),
        decision=AccessDecision(status=AccessStatus.READY),
    )


def _record(key: SourceKey, payload):
    instant = datetime(2026, 9, 24, tzinfo=UTC)
    return ProjectionRecord(
        source_key=key,
        source_release_id=SourceReleaseId('test-release'),
        source_published_at_utc=instant,
        projected_at_utc=instant,
        payload=payload,
    )


def _stores(tmp_path):
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    return ConfigurationManagerStores(
        navigation_source=source,
        tools_source=source,
        access_source=source,
        profiles_source=source,
        kpi_registry_source=source,
        kpi_definitions_source=source,
        navigation=InProcessProjectionStore(),
        tools=InProcessProjectionStore(),
        access=InProcessProjectionStore(),
        profiles=InProcessProjectionStore(),
        kpi_registry=InProcessProjectionStore[KpiRegistry](),
        kpi_definitions=InProcessProjectionStore[KpiDefinitionCatalog](),
        users_registry=InProcessUsersRegistryStore(),
        users_promoted=InProcessUsersAdministrationStore(),
    )


@pytest.mark.parametrize('subject', ['local:jane-doe', 'local:john-doe'])
def test_known_local_users_receive_explicit_manager_permissions(tmp_path, monkeypatch, subject):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    app.secret_key = 'test-only'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    stores = _stores(tmp_path)
    dependencies = compose_integrated_manager_dependencies(
        stores=stores, access_runtime=access_runtime, users_runtime=users_runtime
    )

    with app.test_request_context('/manager'):
        access_runtime.store(_access(subject))
        principal = dependencies.principal_provider()
        surface = ManagerSurface(build_configuration_manager_surface(dependencies))
        visible = surface.registry.visible_items(principal, surface.authorization)

    assert principal.is_local is True
    assert principal.profile_keys == ('local',)
    assert set(principal.access_keys) == set(MANAGER_ACCESS_KEYS)
    assert {item.key for item in visible} == {
        'users',
        'profiles',
        'access',
        'navigation',
        'tools',
        'kpis',
        'kpi-definitions',
    }


@pytest.mark.parametrize(
    ('subject', 'issuer', 'provider'),
    [
        ('local:someone-else', 'atlanticus-local', 'local'),
        ('local:jane-doe', 'test-entra', 'entra'),
        ('local:john-doe', 'test-entra', 'entra'),
    ],
)
def test_untrusted_identity_does_not_inherit_local_administrator(
    tmp_path, monkeypatch, subject, issuer, provider
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    app.secret_key = 'test-only'
    access_runtime = AccessRuntime()
    dependencies = compose_integrated_manager_dependencies(
        stores=_stores(tmp_path),
        access_runtime=access_runtime,
        users_runtime=UsersRuntime(),
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access(subject, issuer=issuer, provider=provider))
        principal = dependencies.principal_provider()
    assert principal.access_keys == ()
    assert principal.is_local is False


def test_production_does_not_enable_local_users(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    app = Flask(__name__)
    app.secret_key = 'test-only'
    access_runtime = AccessRuntime()
    dependencies = compose_integrated_manager_dependencies(
        stores=_stores(tmp_path),
        access_runtime=access_runtime,
        users_runtime=UsersRuntime(),
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access('local:jane-doe'))
        principal = dependencies.principal_provider()
    assert principal.access_keys == ()


def test_managed_user_consumes_active_access_and_profiles_projections(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    app.secret_key = 'test-only'
    stores = _stores(tmp_path)
    stores.profiles.replace_active(_record(PROFILES_CONFIGURATION_SOURCE_KEY, ProfileCatalog()))
    stores.access.replace_active(
        _record(
            ADA_ACCESS_SOURCE_KEY,
            AdaAccessConfiguration(
                access_keys=MANAGER_ACCESS_KEYS,
                profile_access=(
                    ProfileAccessGrant(profile_key='basic', access_keys=('tools.manage',)),
                ),
            ),
        )
    )
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    dependencies = compose_integrated_manager_dependencies(
        stores=stores, access_runtime=access_runtime, users_runtime=users_runtime
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access('managed-1', issuer='test-entra', provider='entra'))
        users_runtime.store(
            load_id='load-1',
            user=EffectiveUser(
                user_id='user-1',
                subject_id='managed-1',
                display_name='Managed user',
                email=None,
                enabled=True,
                avatar_text='MU',
                profile_key='basic',
            ),
        )
        principal = dependencies.principal_provider()
        surface = ManagerSurface(build_configuration_manager_surface(dependencies))
        visible = surface.registry.visible_items(principal, surface.authorization)
    assert principal.access_keys == ('tools.manage',)
    assert {item.key for item in visible} == {'tools'}


def test_missing_projection_denies_managed_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    app.secret_key = 'test-only'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    dependencies = compose_integrated_manager_dependencies(
        stores=_stores(tmp_path),
        access_runtime=access_runtime,
        users_runtime=users_runtime,
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access('managed-1', issuer='test-entra', provider='entra'))
        users_runtime.store(
            load_id='load-1',
            user=EffectiveUser(
                user_id='user-1',
                subject_id='managed-1',
                display_name='Managed user',
                email=None,
                enabled=True,
                avatar_text='MU',
                profile_key='basic',
            ),
        )
        principal = dependencies.principal_provider()
    assert principal.access_keys == ()


def test_invalid_shared_stores_fail_before_manager_composition(tmp_path):
    with pytest.raises(TypeError, match='stores'):
        compose_integrated_manager_dependencies(
            stores=object(), access_runtime=AccessRuntime(), users_runtime=UsersRuntime()
        )


def test_binding_does_not_override_disabled_local_snapshot(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    app.secret_key = 'test-only'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    binding = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
        configuration_provider=lambda: None,
        profiles_provider=lambda: None,
        trusted_local_users=True,
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access('local:jane-doe'))
        users_runtime.store(
            load_id='load-1',
            user=EffectiveUser(
                user_id='user-1',
                subject_id='local:jane-doe',
                display_name='Jane Doe',
                email=None,
                enabled=False,
                avatar_text='JD',
                profile_key='local',
                is_local=True,
            ),
        )
        with pytest.raises(ValueError, match='Disabled user'):
            binding()


@pytest.mark.parametrize('subject', ['local:jane-doe', 'local:john-doe'])
def test_integrated_local_runtime_mounts_authorized_manager(tmp_path, monkeypatch, subject):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', subject)
    stores = _stores(tmp_path)
    dependencies = compose_integrated_manager_dependencies(
        stores=stores,
        access_runtime=AccessRuntime(),
        users_runtime=UsersRuntime(),
    )
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'test_tool',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path / 'tool'),
        }
    )
    runtime = bootstrap.create_operational_application_runtime(
        settings=settings, manager_dependencies=dependencies
    )
    assert runtime.services.contains(ACCESS_RUNTIME_SERVICE_KEY)
    client = runtime.server.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/manager').status_code == 200
    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    serialized = json.dumps(layout.get_json(), ensure_ascii=False)
    assert 'ada-manager-unavailable' not in serialized
    assert 'atlanticus-manager-sidebar' in serialized


def test_explicit_production_environment_disables_local_privileges(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    app.secret_key = 'test-only'
    access_runtime = AccessRuntime()
    dependencies = compose_integrated_manager_dependencies(
        stores=_stores(tmp_path),
        access_runtime=access_runtime,
        users_runtime=UsersRuntime(),
        environment=WebEnvironment.PRODUCTION,
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access('local:jane-doe'))
        principal = dependencies.principal_provider()
    assert principal.access_keys == ()


@pytest.mark.parametrize(
    ('store_name', 'projection_error'),
    [
        ('access', AdaAccessConfigurationProjectionError),
        ('profiles', ProfilesConfigurationProjectionError),
    ],
)
def test_injected_cosmos_failures_are_normalized_for_managed_user(
    tmp_path, monkeypatch, store_name, projection_error
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')

    class UnavailableProjection(InProcessProjectionStore):
        def get_active(self, _source_key):
            try:
                raise CosmosOperationError('private-connection-detail')
            except CosmosOperationError as error:
                raise projection_error('Projection is unavailable') from error

    stores = replace(_stores(tmp_path), **{store_name: UnavailableProjection()})
    app = Flask(__name__)
    app.secret_key = 'test-only'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    dependencies = compose_integrated_manager_dependencies(
        stores=stores,
        access_runtime=access_runtime,
        users_runtime=users_runtime,
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access('managed-1', issuer='test-entra', provider='entra'))
        users_runtime.store(
            load_id='load-1',
            user=EffectiveUser(
                user_id='user-1',
                subject_id='managed-1',
                display_name='Managed user',
                email=None,
                enabled=True,
                avatar_text='MU',
                profile_key='basic',
            ),
        )
        with pytest.raises(ProjectionStoreError, match='provider is unavailable') as caught:
            dependencies.principal_provider()
    assert 'private-connection-detail' not in str(caught.value)
