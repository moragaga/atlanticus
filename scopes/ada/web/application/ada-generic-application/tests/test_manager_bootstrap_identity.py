from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic import bootstrap
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import UserRecord
from atlanticus.web.users.runtime import USERS_RUNTIME_SERVICE_KEY, UsersRuntime
from atlanticus.web.users.store import UsersAdministrationStore, UsersRuntimeStore


def _settings(tmp_path, *, environment='local') -> AdaGenericSettings:
    return AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': environment,
            'ADA_TOOL_NAMESPACE': 'bootstrap_identity',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path / 'tool'),
        }
    )


class SharedPromotedStore(UsersRuntimeStore, UsersAdministrationStore):
    def __init__(self, records=()):
        self.records = {record.user_id: record for record in records}

    def resolve(self, identity):
        return self.get(build_user_key(issuer=identity.issuer, subject_id=identity.subject_id))

    def get(self, user_id):
        return self.records.get(user_id)

    def list_users(self):
        return tuple(self.records.values())

    def create(self, user):
        self.records[user.user_id] = user
        return user

    def replace(self, user):
        self.records[user.user_id] = user
        return user


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
    assert isinstance(
        runtime.services.require(USERS_RUNTIME_SERVICE_KEY, UsersRuntime), UsersRuntime
    )
    client = runtime.server.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/manager').status_code == 200
    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    rendered = json.dumps(layout.get_json())
    assert 'atlanticus-manager-sidebar' in rendered
    assert 'ada-manager-unavailable' not in rendered
    assert set(runtime.page_modules) >= {
        'ada.web.application.configuration_manager.pages.manager',
        'ada.web.application.configuration_manager.pages.module',
    }


def test_shared_managed_root_gets_manager_administration_without_ada_access_projection(
    tmp_path, monkeypatch
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.chdir(tmp_path)
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'sources')
    record = UserRecord(
        user_id=build_user_key(issuer='test', subject_id='managed'),
        issuer='test',
        subject_id='managed',
        display_name='Managed test user',
        email=None,
        enabled=True,
        profile_key='root',
    )
    shared = SharedPromotedStore((record,))
    stores = replace(stores, users_promoted=shared)
    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path),
        manager_stores=stores,
        identity_provider=FixedIdentityProvider(),
    )
    client = runtime.server.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/manager').status_code == 200
    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    rendered = json.dumps(layout.get_json())
    assert 'atlanticus-manager-sidebar' in rendered
    assert 'tools' in rendered
    assert 'ada-manager-unavailable' not in rendered


def test_disabled_managed_user_is_rejected_in_integrated_identity(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.chdir(tmp_path)
    record = UserRecord(
        user_id=build_user_key(issuer='test', subject_id='managed'),
        issuer='test',
        subject_id='managed',
        display_name='Disabled test user',
        email=None,
        enabled=False,
        profile_key='basic',
    )
    stores = replace(
        create_local_configuration_manager_stores(source_root=tmp_path / 'sources'),
        users_promoted=SharedPromotedStore((record,)),
    )
    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path),
        manager_stores=stores,
        identity_provider=FixedIdentityProvider(),
    )
    assert runtime.server.test_client().get('/manager').status_code == 403


def test_non_local_identity_without_shared_users_store_fails_before_tool(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'sources')

    def fail_tool(_settings):
        raise AssertionError('Tool must not be initialized')

    monkeypatch.setattr(bootstrap, '_resolve_tool_projection', fail_tool)
    with pytest.raises(ValueError, match='shared Users runtime store'):
        bootstrap.create_operational_application_runtime(
            settings=_settings(tmp_path),
            manager_stores=stores,
            identity_provider=FixedIdentityProvider(),
        )


def test_local_identity_cannot_be_used_for_production_manager(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'sources')
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')

    def fail_tool(_settings):
        raise AssertionError('Tool must not be initialized')

    monkeypatch.setattr(bootstrap, '_resolve_tool_projection', fail_tool)
    with pytest.raises(RuntimeError, match='production identity provider'):
        bootstrap.create_operational_application_runtime(
            settings=_settings(tmp_path, environment='production'),
            manager_stores=stores,
            identity_provider=LocalIdentityProvider(subject_id='local:jane-doe'),
        )


def test_dual_injection_is_rejected_before_tool(tmp_path, monkeypatch):
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
