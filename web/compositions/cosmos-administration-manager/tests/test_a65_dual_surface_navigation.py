from __future__ import annotations

import re

from dash import page_registry

from atlanticus.connectivity.cosmos.inventory import CosmosContainerProperties
from atlanticus.web.compositions.deployment_access_manager import ROOT_LOGIN_PATH
from atlanticus.web.cosmos_administration import (
    CosmosAdministrationService,
    CosmosConnectionInfo,
    CosmosInventoryReport,
)
from atlanticus.web.profiles.models import BASIC_PROFILE
from atlanticus.web.users.local import LOCAL_JANE, LOCAL_JOHN
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser
from atlanticus.web.users.store import UsersRuntimeStore
from qualification.runtime import DEMO_PASSWORD, DEMO_USER, build_qualification_runtime


class Inventory(CosmosAdministrationService):
    def __init__(self):
        self.calls = []

    def list_connections(self):
        return (CosmosConnectionInfo('primary', 'local-db'),)

    def inventory(self, *, connection_ref, max_items=200):
        return CosmosInventoryReport(
            connection_ref=connection_ref,
            database_name='local-db',
            containers=(CosmosContainerProperties('records', ('/tenant',), 3600),),
        )


class RevocableUsers(UsersRuntimeStore):
    def __init__(self):
        self.user = LOCAL_JANE.to_runtime_user()

    def resolve(self, _identity):
        return self.user

    def list_users(self):
        return (self.user,)

    def replace_all(self, _users):
        raise RuntimeError('Qualification users cannot be modified')


def _page(path):
    return next(page for page in page_registry.values() if page.get('path') == path)


def test_jane_uses_operational_layout_and_manager_pages_without_second_login(
    tmp_path, monkeypatch
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    runtime = build_qualification_runtime(
        directory=tmp_path, administration=Inventory(), local_user='jane'
    )
    client = runtime.web.server.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/manager').status_code == 200
    assert client.get('/manager/cosmos-administration').status_code == 200
    assert client.get('/manager/deployment-access').status_code == 200
    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    assert 'atlanticus-manager-location' not in layout.get_data(as_text=True)
    assert '_pages_content' in layout.get_data(as_text=True)
    dependencies = client.get('/_dash-dependencies').get_json()
    assert any('_pages_content' in row['output'] for row in dependencies)
    assert any('cosmos-administration-report' in row['output'] for row in dependencies)
    assert any('deployment-access-status' in row['output'] for row in dependencies)

    with runtime.web.server.test_request_context('/_dash-update-component'):
        for path in (
            '/manager',
            '/manager/deployment-access',
            '/manager/cosmos-administration',
        ):
            mounted = _page(path)['layout']()
            assert getattr(mounted, 'className', None) == (
                'atlanticus-manager atlanticus-manager--surface'
            )

    assert client.get('/').status_code == 200
    assert 'atlanticus-manager-location' not in client.get('/_dash-layout').get_data(as_text=True)


def test_independent_root_receives_only_manager_without_operational_access(
    tmp_path, monkeypatch
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    runtime = build_qualification_runtime(directory=tmp_path, administration=Inventory())
    client = runtime.web.server.test_client()
    assert client.get('/').status_code == 401
    form = client.get(ROOT_LOGIN_PATH).get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([\w-]+)"', form)
    assert token is not None
    login = client.post(
        ROOT_LOGIN_PATH,
        data={
            'csrf_token': token.group(1),
            'service_user': DEMO_USER,
            'password': DEMO_PASSWORD,
        },
    )
    assert login.status_code == 303
    assert client.get('/manager').status_code == 200
    layout = client.get('/_dash-layout')
    assert 'atlanticus-manager-location' in layout.get_data(as_text=True)
    dependencies = client.get('/_dash-dependencies').get_json()
    assert not any('_pages_content' in item['output'] for item in dependencies)
    assert all(
        'atlanticus-manager-' in item['output']
        or 'atlanticus-deployment-access-manager-' in item['output']
        or 'atlanticus-cosmos-admin-' in item['output']
        for item in dependencies
    )
    assert client.get('/').status_code == 401


def test_revoked_local_root_cannot_render_manager_pages_or_run_manager_callbacks(
    tmp_path, monkeypatch
):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    users = RevocableUsers()
    runtime = build_qualification_runtime(
        directory=tmp_path,
        administration=Inventory(),
        local_user='jane',
        local_users=users,
    )
    client = runtime.web.server.test_client()
    response = client.get('/_dash-dependencies')
    assert response.status_code == 200
    output = next(
        row['output']
        for row in response.get_json()
        if row['output'].endswith('cosmos-administration-report.children')
    )
    users.user = RuntimeUser(
        identity=users.user.identity,
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
    )
    with runtime.web.server.test_request_context('/_dash-update-component'):
        assert _page('/manager')['layout']().children == 'Manager access denied'
    assert client.get('/manager').status_code != 200
    assert client.post('/_dash-update-component', json={'output': output}).status_code == 403
    assert not any(
        item['output'] == output for item in client.get('/_dash-dependencies').get_json()
    )


def _manager_entry_content(client) -> str:
    assert client.get('/manager/deployment-access').status_code == 200
    response = client.post(
        '/_dash-update-component',
        json={
            'output': 'atlanticus-manager-content.children',
            'outputs': {
                'id': 'atlanticus-manager-content',
                'property': 'children',
            },
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
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_manager_page_dispatch_is_isolated_by_flask_application(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    (tmp_path / 'jane').mkdir()
    (tmp_path / 'john').mkdir()
    jane = build_qualification_runtime(
        directory=tmp_path / 'jane', administration=Inventory(), local_user='jane'
    )
    john = build_qualification_runtime(
        directory=tmp_path / 'john', administration=Inventory(), local_user='john'
    )
    for runtime in (jane, john):
        with runtime.web.server.test_request_context('/_dash-update-component'):
            page = _page('/manager/deployment-access')['layout']()
            assert getattr(page, 'className', None) == (
                'atlanticus-manager atlanticus-manager--surface'
            )
    jane_content = _manager_entry_content(jane.web.server.test_client())
    john_content = _manager_entry_content(john.web.server.test_client())
    assert f'Identidad: {LOCAL_JANE.display_name}.' in jane_content
    assert f'Identidad: {LOCAL_JOHN.display_name}.' in john_content
    assert f'Identidad: {LOCAL_JOHN.display_name}.' not in jane_content
    assert f'Identidad: {LOCAL_JANE.display_name}.' not in john_content
