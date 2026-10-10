from __future__ import annotations

import re

import pytest
from flask import Flask, Request

from atlanticus.connectivity.cosmos.inventory import CosmosContainerProperties
from atlanticus.web.compositions.cosmos_administration_manager import (
    create_authenticated_root_provider,
)
from atlanticus.web.cosmos_administration import (
    CosmosAdministrationService,
    CosmosConnectionInfo,
    CosmosInventoryReport,
)
from atlanticus.web.identity.local.provider import LocalIdentityProvider
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.local import LOCAL_JANE, LOCAL_JOHN
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser
from atlanticus.web.users.store import UsersRuntimeStore
from qualification.runtime import DEMO_PASSWORD, DEMO_USER, build_qualification_runtime


class LiveUsers(UsersRuntimeStore):
    def __init__(self, user):
        self.user = user

    def resolve(self, _identity):
        return self.user

    def list_users(self):
        return (self.user,) if self.user is not None else ()

    def replace_all(self, _users):
        raise RuntimeError('Test store is read-only')


class EntraProvider(IdentityProvider):
    @property
    def key(self):
        return 'entra'

    @property
    def production_ready(self):
        return True

    def validate_configuration(self):
        return None

    def resolve(self, _request: Request):
        return AuthenticatedIdentity(provider_key='entra', issuer='tenant', subject_id='alice')


class Inventory(CosmosAdministrationService):
    def __init__(self):
        self.calls = []

    def list_connections(self):
        return (CosmosConnectionInfo('primary', 'test-db'),)

    def inventory(self, *, connection_ref, max_items=200):
        self.calls.append((connection_ref, max_items))
        return CosmosInventoryReport(
            connection_ref=connection_ref,
            database_name='test-db',
            containers=(CosmosContainerProperties('users', ('/tenant',), 3600),),
        )


@pytest.mark.parametrize('local_user', ('jane', 'john'))
def test_local_root_direct_manager_without_material_login(tmp_path, monkeypatch, local_user):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    administration = Inventory()
    runtime = build_qualification_runtime(
        directory=tmp_path, administration=administration, local_user=local_user
    )
    client = runtime.web.server.test_client()
    for route in ('/manager', '/manager/cosmos-administration', '/manager/deployment-access'):
        assert client.get(route).status_code == 200
    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    assert 'Cosmos Administration' in layout.get_data(as_text=True)
    assert 'Deployment Access' in layout.get_data(as_text=True)
    assert administration.calls == []
    assert client.get('/manager/foreign').status_code != 200
    assert client.get('/').status_code == 200
    assert (
        client.post('/_dash-update-component', json={'output': 'foreign.callback'}).status_code
        != 200
    )


def test_local_root_can_inspect_and_material_logout_does_not_revoke_local(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    administration = Inventory()
    runtime = build_qualification_runtime(
        directory=tmp_path, administration=administration, local_user='jane'
    )
    client = runtime.web.server.test_client()
    dependencies = client.get('/_dash-dependencies').get_json()
    assert any(
        item['output'].endswith('cosmos-administration-report.children') for item in dependencies
    )
    response = client.post(
        '/_dash-update-component',
        json={
            'output': 'atlanticus-cosmos-admin-cosmos-administration-report.children',
            'outputs': {
                'id': 'atlanticus-cosmos-admin-cosmos-administration-report',
                'property': 'children',
            },
            'inputs': [
                {
                    'id': 'atlanticus-cosmos-admin-cosmos-administration-inspect',
                    'property': 'n_clicks',
                    'value': 1,
                }
            ],
            'state': [
                {
                    'id': 'atlanticus-cosmos-admin-cosmos-administration-connection',
                    'property': 'value',
                    'value': 'primary',
                }
            ],
            'changedPropIds': ['atlanticus-cosmos-admin-cosmos-administration-inspect.n_clicks'],
        },
    )
    assert response.status_code == 200
    assert administration.calls == [('primary', 200)]
    page = client.get('/manager-root/login')
    token = re.search(r'name="csrf_token" value="([\w-]+)"', page.get_data(as_text=True)).group(1)
    logged = client.post(
        '/manager-root/login',
        data={
            'csrf_token': token,
            'service_user': DEMO_USER,
            'password': DEMO_PASSWORD,
        },
    )
    assert logged.status_code == 303
    status = client.get('/manager-root/status')
    token = re.search(r'name="csrf_token" value="([\w-]+)"', status.get_data(as_text=True)).group(1)
    assert client.post('/manager-root/logout', data={'csrf_token': token}).status_code == 303
    assert client.get('/manager').status_code == 200


@pytest.mark.parametrize('person', (LOCAL_JANE, LOCAL_JOHN))
def test_local_profile_has_full_access_and_preserves_local_label(monkeypatch, person):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    app.secret_key = 'test-only'
    provider = create_authenticated_root_provider(
        identity_provider=LocalIdentityProvider(subject_id=person.subject_id),
        users=LiveUsers(person.to_runtime_user()),
    )
    with app.test_request_context('/manager'):
        principal = provider()
        assert principal is not None
        assert principal.administrative_override is True
        assert principal.profile_label == 'Local'
        assert principal.is_local is True
        assert principal.subject_id == person.user_id


def test_local_profile_is_not_accepted_with_nonlocal_provider(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    provider = create_authenticated_root_provider(
        identity_provider=EntraProvider(), users=LiveUsers(LOCAL_JANE.to_runtime_user())
    )
    with app.test_request_context('/manager'):
        assert provider() is None


def test_root_privilege_revocation_disabling_and_mismatch(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    from atlanticus.web.users.identity import build_user_key
    from atlanticus.web.users.models import UserIdentity

    user = RuntimeUser(
        identity=UserIdentity(
            user_id=build_user_key(issuer='tenant', subject_id='alice'),
            issuer='tenant',
            subject_id='alice',
            display_name='Alice',
        ),
        enabled=True,
        profile=RuntimeProfile.from_profile(ROOT_PROFILE),
    )
    store = LiveUsers(user)
    provider = create_authenticated_root_provider(identity_provider=EntraProvider(), users=store)
    app = Flask(__name__)
    with app.test_request_context('/manager'):
        principal = provider()
        assert principal is not None
        assert principal.profile_label == 'Root'
        store.user = RuntimeUser(
            identity=user.identity, enabled=True, profile=RuntimeProfile.from_profile(BASIC_PROFILE)
        )
        assert provider() is None
        store.user = RuntimeUser(
            identity=user.identity, enabled=False, profile=RuntimeProfile.from_profile(ROOT_PROFILE)
        )
        assert provider() is None
        store.user = LOCAL_JANE.to_runtime_user()
        assert provider() is None


def test_local_provider_fails_closed_in_production(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    app = Flask(__name__)
    provider = create_authenticated_root_provider(
        identity_provider=LocalIdentityProvider(subject_id=LOCAL_JANE.subject_id),
        users=LiveUsers(LOCAL_JANE.to_runtime_user()),
    )
    with app.test_request_context('/manager'):
        assert provider() is None


def test_revoked_local_root_blocks_manager_and_callbacks(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    store = LiveUsers(LOCAL_JANE.to_runtime_user())
    administration = Inventory()
    runtime = build_qualification_runtime(
        directory=tmp_path, administration=administration, local_user='jane', local_users=store
    )
    client = runtime.web.server.test_client()
    assert client.get('/manager/cosmos-administration').status_code == 200
    outputs = client.get('/_dash-dependencies').get_json()
    output = next(
        row['output']
        for row in outputs
        if row['output'].endswith('cosmos-administration-report.children')
    )
    store.user = RuntimeUser(
        identity=store.user.identity,
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
    )
    assert client.get('/manager/cosmos-administration').status_code != 200
    dependencies = client.get('/_dash-dependencies')
    assert dependencies.status_code == 200
    assert all(row['output'] != output for row in dependencies.get_json())
    assert client.post('/_dash-update-component', json={'output': output}).status_code == 403
    assert administration.calls == []
