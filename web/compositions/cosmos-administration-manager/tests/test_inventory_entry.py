from __future__ import annotations

import pytest
from dash.exceptions import PreventUpdate
from flask import Flask

from atlanticus.connectivity.cosmos.inventory import CosmosContainerProperties
from atlanticus.web.compositions.cosmos_administration_manager import (
    CosmosInventoryManagerEntryError,
    create_cosmos_inventory_manager_entry,
)
from atlanticus.web.compositions.deployment_access_manager import DeploymentRootSession
from atlanticus.web.cosmos_administration import (
    CosmosAdministrationService,
    CosmosConnectionInfo,
    CosmosInventoryReport,
)
from atlanticus.web.deployment_access import (
    DeploymentAccessAuthentication,
    DeploymentAccessIdentity,
    DeploymentAccessMaterialError,
    DeploymentAccessService,
    DeploymentAccessStatus,
    MaterialAvailability,
)
from atlanticus.web.manager import (
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
)
from atlanticus.web.services import ServiceRegistry


class FakeAccess(DeploymentAccessService):
    def __init__(self):
        self.fingerprint = 'a' * 64

    def authenticate(self, *, service_user, password):
        if (service_user, password) != ('root', 'correct-password-for-testing'):
            raise DeploymentAccessMaterialError('Invalid credentials')
        return DeploymentAccessAuthentication(
            identity=DeploymentAccessIdentity('b' * 32, 'root', 'demo', 'local'),
            fingerprint=self.fingerprint,
        )

    def inspect(self):
        return DeploymentAccessStatus(MaterialAvailability.PRESENT, self.fingerprint)


class FakeAdministration(CosmosAdministrationService):
    def __init__(self):
        self.list_calls = 0
        self.inventory_calls = []
        self.failed = False

    def list_connections(self):
        self.list_calls += 1
        return (
            CosmosConnectionInfo('analytics', 'analytics-db'),
            CosmosConnectionInfo('primary', 'main-db'),
        )

    def inventory(self, *, connection_ref, max_items=200):
        self.inventory_calls.append((connection_ref, max_items))
        if self.failed:
            raise ValueError('secret connection key must never be exposed')
        return CosmosInventoryReport(
            connection_ref=connection_ref,
            database_name='main-db' if connection_ref == 'primary' else 'analytics-db',
            containers=(
                CosmosContainerProperties('users', ('/tenant',), None, etag='private-etag'),
                CosmosContainerProperties('events', ('/pk',), 3600),
            ),
        )


class FakeDash:
    def __init__(self):
        self.callbacks = []

    def callback(self, *_args, **_kwargs):
        def register(function):
            self.callbacks.append(function)
            return function

        return register


class DenyAll:
    def can_view(self, _principal, _entry):
        return False


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, (tuple, list)):
        return ' '.join(_text(item) for item in value)
    children = getattr(value, 'children', None)
    return '' if children is None else _text(children)


def _build(*, policy=None, fallback_override=False):
    server = Flask(__name__)
    server.secret_key = 'cosmos-inventory-tests-only'
    administration = FakeAdministration()
    access = FakeAccess()
    root = DeploymentRootSession(access=access)

    def principal():
        return ManagerPrincipal(
            subject_id='ordinary-admin',
            display_name='Ordinary admin',
            administrative_override=fallback_override or root.current() is not None,
        )

    entry = create_cosmos_inventory_manager_entry(
        administration=administration,
        root_session=root,
        principal_provider=principal,
        group_key='administration',
        max_items=25,
        authorization=policy,
    )
    app = FakeDash()
    entry.web_module.register_callbacks(app, ServiceRegistry())
    return server, administration, access, root, entry, app.callbacks[0]


def test_entry_uses_manager_registry_and_does_not_read_inventory_on_layout():
    server, administration, _access, root, entry, callback = _build()
    registry = ManagerModuleRegistry(
        (ManagerModuleGroup(key='administration', title='Administration', order=1),),
        (),
        entries=(entry,),
        route_prefix='/manager',
    )
    assert registry.route_for(entry) == '/manager/cosmos-administration'
    with server.test_request_context('/manager'):
        root.login(service_user='root', password='correct-password-for-testing')
        layout = entry.layout(ServiceRegistry())
        assert 'Inventario de solo lectura' in _text(layout)
        assert administration.list_calls == 1
        assert administration.inventory_calls == []
        with pytest.raises(PreventUpdate):
            callback(0, 'primary')
        assert administration.inventory_calls == []


def test_root_session_required_even_for_regular_administrative_override():
    server, administration, _access, _root, entry, callback = _build(fallback_override=True)
    with server.test_request_context('/manager'):
        assert 'sesión ROOT' in _text(entry.layout(ServiceRegistry()))
        assert 'sesión ROOT' in _text(callback(1, 'primary'))
    assert administration.list_calls == 0
    assert administration.inventory_calls == []


def test_inventory_uses_selected_named_connection_and_hides_etag():
    server, administration, _access, root, _entry, callback = _build()
    with server.test_request_context('/_dash-update-component'):
        root.login(service_user='root', password='correct-password-for-testing')
        assert 'Selecciona una conexión' in _text(callback(1, 'unknown'))
        assert administration.inventory_calls == []
        data = _text(callback(2, 'primary'))
        assert 'main-db' in data
        assert 'users' in data
        assert '/tenant' in data
        assert '3600' in data
        assert 'private-etag' not in data
        assert administration.inventory_calls == [('primary', 25)]


def test_rotation_blocks_callbacks_before_inventory():
    server, administration, access, root, _entry, callback = _build()
    with server.test_request_context('/_dash-update-component'):
        root.login(service_user='root', password='correct-password-for-testing')
        access.fingerprint = 'c' * 64
        assert 'sesión ROOT' in _text(callback(1, 'primary'))
    assert administration.inventory_calls == []


def test_manager_authorization_is_enforced_and_backend_errors_are_not_disclosed():
    server, administration, _access, root, entry, callback = _build(policy=DenyAll())
    with server.test_request_context('/manager'):
        root.login(service_user='root', password='correct-password-for-testing')
        assert 'autorización Manager' in _text(entry.layout(ServiceRegistry()))
        assert 'autorización Manager' in _text(callback(1, 'primary'))
    assert administration.inventory_calls == []

    server, administration, _access, root, _entry, callback = _build()
    with server.test_request_context('/_dash-update-component'):
        root.login(service_user='root', password='correct-password-for-testing')
        administration.failed = True
        assert 'No fue posible consultar' in _text(callback(1, 'primary'))
        assert 'secret connection' not in _text(callback(1, 'primary'))


def test_invalid_configuration_rejected():
    _server, administration, _access, root, _entry, _callback = _build()

    def principal():
        return ManagerPrincipal(subject_id='x', display_name='X')

    values = (
        {'administration': object()},
        {'root_session': object()},
        {'principal_provider': None},
        {'max_items': True},
        {'max_items': 201},
    )
    for change in values:
        arguments = {
            'administration': administration,
            'root_session': root,
            'principal_provider': principal,
            'group_key': 'administration',
        }
        arguments.update(change)
        with pytest.raises(CosmosInventoryManagerEntryError):
            create_cosmos_inventory_manager_entry(**arguments)
