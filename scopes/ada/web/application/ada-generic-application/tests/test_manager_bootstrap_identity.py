from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ada.web.application.configuration_manager.local_runtime import (
    InProcessUsersRuntimeStore,
    create_local_configuration_manager_stores,
)
from ada.web.application.generic import bootstrap
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.runtime import USERS_RUNTIME_SERVICE_KEY, UsersRuntime


def _settings(tmp_path, *, environment='local'):
    return AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': environment,
            'ADA_TOOL_NAMESPACE': 'bootstrap_identity',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path / 'tool'),
        }
    )


class FixedIdentityProvider(IdentityProvider):
    @property
    def key(self):
        return 'fixed'

    @property
    def production_ready(self):
        return True

    def validate_configuration(self):
        return None

    def resolve(self, request):
        del request
        return AuthenticatedIdentity(provider_key='fixed', issuer='test', subject_id='managed')


def _runtime_user(*, root=False, enabled=True):
    identity = UserIdentity(
        user_id=build_user_key(issuer='test', subject_id='managed'),
        issuer='test',
        subject_id='managed',
        display_name='Managed test user',
    )
    return RuntimeUser(
        identity=identity,
        enabled=enabled,
        profile=RuntimeProfile.from_profile(ROOT_PROFILE if root else BASIC_PROFILE),
    )


@pytest.mark.parametrize('subject', ['local:jane-doe', 'local:john-doe'])
def test_known_local_user_is_authorized_from_real_bootstrap(tmp_path, monkeypatch, subject):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.chdir(tmp_path)
    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path),
        manager_stores=create_local_configuration_manager_stores(
            source_root=tmp_path / 'configuration-source'
        ),
        identity_provider=LocalIdentityProvider(subject_id=subject),
    )
    assert isinstance(runtime.services.require(USERS_RUNTIME_SERVICE_KEY, UsersRuntime), UsersRuntime)
    client = runtime.server.test_client()
    assert client.get('/manager').status_code == 200


def test_root_runtime_user_gets_manager_administration_without_access_projection(
    tmp_path, monkeypatch
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.chdir(tmp_path)
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'sources')
    stores = replace(
        stores,
        users_runtime=InProcessUsersRuntimeStore((_runtime_user(root=True),)),
    )
    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path),
        manager_stores=stores,
        identity_provider=FixedIdentityProvider(),
    )
    client = runtime.server.test_client()
    assert client.get('/manager').status_code == 200
    rendered = json.dumps(client.get('/_dash-layout').get_json())
    assert 'tools' in rendered


def test_disabled_runtime_user_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = replace(
        create_local_configuration_manager_stores(source_root=tmp_path / 'sources'),
        users_runtime=InProcessUsersRuntimeStore((_runtime_user(enabled=False),)),
    )
    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path),
        manager_stores=stores,
        identity_provider=FixedIdentityProvider(),
    )
    assert runtime.server.test_client().get('/manager').status_code == 403


def test_local_identity_cannot_be_used_for_production_manager(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'sources')
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    monkeypatch.setattr(
        bootstrap,
        '_resolve_tool_projection',
        lambda _settings: (_ for _ in ()).throw(AssertionError('Tool must not initialize')),
    )
    with pytest.raises(RuntimeError, match='production identity provider'):
        bootstrap.create_operational_application_runtime(
            settings=_settings(tmp_path, environment='production'),
            manager_stores=stores,
            identity_provider=LocalIdentityProvider(subject_id='local:jane-doe'),
        )


def test_dual_manager_injection_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'sources')
    dependencies = bootstrap.compose_integrated_manager_dependencies(
        stores=stores,
        access_runtime=bootstrap.AccessRuntime(),
        users_runtime=UsersRuntime(),
    )
    with pytest.raises(ValueError, match='not both'):
        bootstrap.create_operational_application_runtime(
            settings=_settings(tmp_path),
            manager_stores=stores,
            manager_dependencies=dependencies,
        )
