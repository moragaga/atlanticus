from __future__ import annotations

import re

from atlanticus.connectivity.cosmos.inventory import CosmosContainerProperties
from atlanticus.web.compositions.deployment_access_manager import (
    ROOT_LOGIN_PATH,
    ROOT_LOGOUT_PATH,
    ROOT_STATUS_PATH,
)
from atlanticus.web.cosmos_administration import (
    CosmosAdministrationService,
    CosmosConnectionInfo,
    CosmosInventoryReport,
)
from qualification.runtime import DEMO_PASSWORD, DEMO_USER, build_qualification_runtime


class FakeAdministration(CosmosAdministrationService):
    def __init__(self):
        self.list_calls = 0
        self.inventory_calls = []

    def list_connections(self):
        self.list_calls += 1
        return (
            CosmosConnectionInfo('primary', 'main-db'),
            CosmosConnectionInfo('analytics', 'analytics-db'),
        )

    def inventory(self, *, connection_ref, max_items=200):
        self.inventory_calls.append((connection_ref, max_items))
        return CosmosInventoryReport(
            connection_ref=connection_ref,
            database_name='main-db' if connection_ref == 'primary' else 'analytics-db',
            containers=(
                CosmosContainerProperties(
                    name='users',
                    partition_key_paths=('/tenant',),
                    default_ttl_seconds=3600,
                    etag='private-etag',
                ),
            ),
        )


def _csrf(response):
    found = re.search(r'name="csrf_token" value="([\w-]+)"', response.get_data(as_text=True))
    assert found is not None
    return found.group(1)


def _login(client):
    response = client.post(
        ROOT_LOGIN_PATH,
        data={
            'csrf_token': _csrf(client.get(ROOT_LOGIN_PATH)),
            'service_user': DEMO_USER,
            'password': DEMO_PASSWORD,
        },
    )
    assert response.status_code == 303
    assert response.headers['Location'] == ROOT_STATUS_PATH


def _inventory_callback(client, *, output, clicks=1, connection='primary'):
    target = output.removesuffix('.children')
    return client.post(
        '/_dash-update-component',
        json={
            'output': output,
            'outputs': {'id': target, 'property': 'children'},
            'inputs': [
                {
                    'id': 'atlanticus-cosmos-admin-cosmos-administration-inspect',
                    'property': 'n_clicks',
                    'value': clicks,
                }
            ],
            'state': [
                {
                    'id': 'atlanticus-cosmos-admin-cosmos-administration-connection',
                    'property': 'value',
                    'value': connection,
                }
            ],
            'changedPropIds': ['atlanticus-cosmos-admin-cosmos-administration-inspect.n_clicks'],
        },
    )


def test_real_web_host_shares_root_and_fences_cosmos_inventory(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    administration = FakeAdministration()
    runtime = build_qualification_runtime(directory=tmp_path, administration=administration)
    client = runtime.web.server.test_client()
    other_client = runtime.web.server.test_client()

    assert client.get('/manager').status_code == 401
    assert client.get('/manager/cosmos-administration').status_code == 401
    assert client.get('/manager/deployment-access').status_code == 401
    assert client.get('/_dash-dependencies').status_code == 401
    assert administration.inventory_calls == []

    _login(client)
    assert other_client.get('/manager').status_code == 401
    assert client.get('/manager').status_code == 200
    assert client.get('/manager/cosmos-administration').status_code == 200
    assert client.get('/manager/deployment-access').status_code == 200
    assert client.get('/manager/foreign').status_code == 401
    assert client.get('/').status_code == 401
    assert administration.inventory_calls == []

    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    assert layout.headers['Cache-Control'] == 'private, no-store'
    assert 'Deployment Access' in layout.get_data(as_text=True)
    assert 'Cosmos Administration' in layout.get_data(as_text=True)
    assert administration.inventory_calls == []

    response = client.get('/_dash-dependencies')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'private, no-store'
    dependencies = response.get_json()
    assert isinstance(dependencies, list)
    output = next(
        row['output']
        for row in dependencies
        if row['output'] == 'atlanticus-cosmos-admin-cosmos-administration-report.children'
    )
    assert any(row['output'].endswith('deployment-access-status.children') for row in dependencies)

    invalid = _inventory_callback(client, output=output, connection='not-configured')
    assert invalid.status_code == 200
    assert administration.inventory_calls == []
    read = _inventory_callback(client, output=output, connection='analytics')
    assert read.status_code == 200
    assert 'analytics-db' in read.get_data(as_text=True)
    assert 'users' in read.get_data(as_text=True)
    assert 'private-etag' not in read.get_data(as_text=True)
    assert administration.inventory_calls == [('analytics', 200)]
    assert _inventory_callback(other_client, output=output).status_code == 401
    assert (
        client.post('/_dash-update-component', json={'output': 'foreign.callback'}).status_code
        == 401
    )

    runtime.access.create_or_replace(service_user=DEMO_USER, password=DEMO_PASSWORD)
    assert client.get('/manager/cosmos-administration').status_code == 401
    assert _inventory_callback(client, output=output).status_code == 401
    assert administration.inventory_calls == [('analytics', 200)]

    _login(client)
    status = client.get(ROOT_STATUS_PATH)
    assert status.status_code == 200
    result = client.post(ROOT_LOGOUT_PATH, data={'csrf_token': _csrf(status)})
    assert result.status_code == 303
    assert client.get('/manager').status_code == 401
    assert _inventory_callback(client, output=output).status_code == 401


def test_qualification_cannot_start_outside_local(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    administration = FakeAdministration()
    try:
        build_qualification_runtime(directory=tmp_path, administration=administration)
    except ValueError as error:
        assert str(error) == 'Cosmos ROOT qualification is only available in local environment'
    else:
        raise AssertionError('Production qualification must be rejected')
