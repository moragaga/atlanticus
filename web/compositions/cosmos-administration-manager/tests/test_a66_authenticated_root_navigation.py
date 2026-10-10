from __future__ import annotations

from flask import Request

from atlanticus.connectivity.cosmos.inventory import CosmosContainerProperties
from atlanticus.web.cosmos_administration import (
    CosmosAdministrationService,
    CosmosConnectionInfo,
    CosmosInventoryReport,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.store import UsersRuntimeStore
from qualification.runtime import build_qualification_runtime


class EntraContractProvider(IdentityProvider):
    def __init__(self):
        self.issuer = 'tenant-a'
        self.subject_id = 'alice'

    @property
    def key(self):
        return 'entra-contract-qualification'

    @property
    def production_ready(self):
        return True

    def validate_configuration(self):
        return None

    def resolve(self, _request: Request):
        return AuthenticatedIdentity(
            provider_key=self.key,
            issuer=self.issuer,
            subject_id=self.subject_id,
        )


class MutableUsers(UsersRuntimeStore):
    def __init__(self, user):
        self.user = user

    def resolve(self, identity):
        user = self.user
        if user is None or (user.issuer, user.subject_id) != (
            identity.issuer,
            identity.subject_id,
        ):
            return None
        return user

    def list_users(self):
        return (self.user,) if self.user is not None else ()

    def replace_all(self, _users):
        raise RuntimeError('Qualification users cannot be modified')


class Inventory(CosmosAdministrationService):
    def __init__(self):
        self.calls = []

    def list_connections(self):
        return (CosmosConnectionInfo('primary', 'qualification-db'),)

    def inventory(self, *, connection_ref, max_items=200):
        self.calls.append((connection_ref, max_items))
        return CosmosInventoryReport(
            connection_ref=connection_ref,
            database_name='qualification-db',
            containers=(CosmosContainerProperties('records', ('/tenant',), 3600),),
        )


def _user(*, enabled=True, profile=ROOT_PROFILE):
    issuer = 'tenant-a'
    subject_id = 'alice'
    return RuntimeUser(
        identity=UserIdentity(
            user_id=build_user_key(issuer=issuer, subject_id=subject_id),
            issuer=issuer,
            subject_id=subject_id,
            display_name='Alice Root',
        ),
        enabled=enabled,
        profile=RuntimeProfile.from_profile(profile),
    )


def _runtime(tmp_path):
    provider = EntraContractProvider()
    users = MutableUsers(_user())
    administration = Inventory()
    runtime = build_qualification_runtime(
        directory=tmp_path,
        administration=administration,
        authenticated_provider=provider,
        authenticated_users=users,
    )
    return runtime, provider, users, administration


def _manager_content(client):
    response = client.post(
        '/_dash-update-component',
        json={
            'output': 'atlanticus-manager-content.children',
            'outputs': {'id': 'atlanticus-manager-content', 'property': 'children'},
            'inputs': [
                {
                    'id': 'atlanticus-manager-location',
                    'property': 'pathname',
                    'value': '/manager/deployment-access',
                }
            ],
            'state': [],
            'changedPropIds': ['atlanticus-manager-location.pathname'],
        },
    )
    return response


def test_authenticated_root_navigates_both_surfaces_without_material_login(
    tmp_path, monkeypatch
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    runtime, _provider, _users, administration = _runtime(tmp_path)
    client = runtime.web.server.test_client()

    for path in ('/', '/manager', '/manager/deployment-access', '/manager/cosmos-administration'):
        assert client.get(path).status_code == 200
    assert client.get('/manager-root/status').status_code == 401
    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    assert '_pages_content' in layout.get_data(as_text=True)
    assert 'atlanticus-manager-location' not in layout.get_data(as_text=True)
    dependencies = client.get('/_dash-dependencies').get_json()
    assert any('_pages_content' in row['output'] for row in dependencies)
    assert any(row['output'] == 'atlanticus-manager-content.children' for row in dependencies)
    assert any('cosmos-administration-report' in row['output'] for row in dependencies)

    details = _manager_content(client)
    assert details.status_code == 200
    assert 'Identidad: Alice Root.' in details.get_data(as_text=True)
    assert 'Perfil: Root.' in details.get_data(as_text=True)
    assert administration.calls == []
    assert client.get('/').status_code == 200


def test_root_revocation_blocks_administration_but_preserves_operational_identity(
    tmp_path, monkeypatch
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    runtime, provider, users, _administration = _runtime(tmp_path)
    client = runtime.web.server.test_client()
    assert client.get('/manager').status_code == 200
    assert _manager_content(client).status_code == 200

    users.user = _user(profile=BASIC_PROFILE)
    assert client.get('/').status_code == 200
    assert client.get('/manager').status_code != 200
    assert client.get('/manager/deployment-access').status_code != 200
    deps = client.get('/_dash-dependencies').get_json()
    assert any('_pages_content' in row['output'] for row in deps)
    assert not any(row['output'] == 'atlanticus-manager-content.children' for row in deps)
    assert _manager_content(client).status_code == 403

    users.user = _user(enabled=False)
    assert client.get('/manager').status_code != 200
    users.user = _user()
    provider.issuer = 'tenant-b'
    assert client.get('/manager').status_code != 200
    assert _manager_content(client).status_code == 403
    provider.issuer = 'tenant-a'
    assert client.get('/manager').status_code == 200


def test_qualification_requires_one_identity_mode(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    administration = Inventory()
    provider = EntraContractProvider()
    users = MutableUsers(_user())
    with pytest.raises(ValueError, match='configured together'):
        build_qualification_runtime(
            directory=tmp_path,
            administration=administration,
            authenticated_provider=provider,
        )
    with pytest.raises(ValueError, match='cannot be combined'):
        build_qualification_runtime(
            directory=tmp_path,
            administration=administration,
            local_user='jane',
            authenticated_provider=provider,
            authenticated_users=users,
        )
