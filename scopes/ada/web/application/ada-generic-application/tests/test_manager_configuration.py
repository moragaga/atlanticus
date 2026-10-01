from __future__ import annotations

import json
from dataclasses import replace

import pytest
from flask import Flask

from ada.web.application.configuration_manager.composition import (
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.local_runtime import (
    InProcessProjectionStore,
    InProcessUsersAdministrationStore,
    InProcessUsersRegistryStore,
)
from ada.web.application.configuration_manager.wiring import ConfigurationManagerStores
from ada.web.application.generic import bootstrap
from ada.web.application.generic.manager_principal import (
    ManagerPrincipalBinding,
    compose_integrated_manager_dependencies,
)
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.registry.models import KpiRegistry
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
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.runtime import UsersRuntime


def _access(subject: str, *, issuer: str = 'atlanticus-local', provider: str = 'local'):
    return AccessSnapshot.resolved(
        load_id='load-1',
        identity=AuthenticatedIdentity(provider_key=provider, issuer=issuer, subject_id=subject),
        decision=AccessDecision(status=AccessStatus.READY),
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
def test_known_local_users_receive_manager_administrative_override(
    tmp_path, monkeypatch, subject
):
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
    assert principal.access_keys == ()
    assert principal.administrative_override is True
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
    assert principal.administrative_override is False
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
    assert principal.administrative_override is False


def test_managed_root_receives_manager_administration_without_ada_access_projection(
    tmp_path, monkeypatch
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    app.secret_key = 'test-only'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    dependencies = compose_integrated_manager_dependencies(
        stores=_stores(tmp_path), access_runtime=access_runtime, users_runtime=users_runtime
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access('managed-1', issuer='test-entra', provider='entra'))
        users_runtime.store(
            load_id='load-1',
            user=EffectiveUser(
                user_id='user-1',
                subject_id='managed-1',
                display_name='Managed root',
                email=None,
                enabled=True,
                avatar_text='MR',
                profile_key='root',
            ),
        )
        principal = dependencies.principal_provider()
        surface = ManagerSurface(build_configuration_manager_surface(dependencies))
        visible = surface.registry.visible_items(principal, surface.authorization)

    assert principal.access_keys == ()
    assert principal.administrative_override is True
    assert {item.key for item in visible} == {
        'users',
        'profiles',
        'access',
        'navigation',
        'tools',
        'kpis',
        'kpi-definitions',
    }


def test_managed_basic_has_no_manager_permissions_without_projection_dependency(
    tmp_path, monkeypatch
):
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
                display_name='Managed basic',
                email=None,
                enabled=True,
                avatar_text='MB',
                profile_key='basic',
            ),
        )
        principal = dependencies.principal_provider()
        surface = ManagerSurface(build_configuration_manager_surface(dependencies))
        visible = surface.registry.visible_items(principal, surface.authorization)

    assert principal.access_keys == ()
    assert principal.administrative_override is False
    assert visible == ()


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
    assert principal.administrative_override is False


def test_access_and_profiles_projection_failures_do_not_affect_manager_principal(
    tmp_path, monkeypatch
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')

    class ForbiddenProjectionRead(InProcessProjectionStore):
        def get_active(self, _source_key):
            raise AssertionError('Manager principal must not read ADA Access or Profiles projections')

    stores = replace(
        _stores(tmp_path),
        access=ForbiddenProjectionRead(),
        profiles=ForbiddenProjectionRead(),
    )
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
                display_name='Managed root',
                email=None,
                enabled=True,
                avatar_text='MR',
                profile_key='root',
            ),
        )
        principal = dependencies.principal_provider()

    assert principal.access_keys == ()
    assert principal.administrative_override is True
