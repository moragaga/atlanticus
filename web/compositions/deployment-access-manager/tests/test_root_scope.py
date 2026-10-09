from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from flask import Flask, Request, jsonify

from atlanticus.web.compositions.deployment_access_manager import (
    ROOT_INDEPENDENT_ROUTES,
    ROOT_LOGIN_PATH,
    DeploymentRootSession,
    RootManagerRequestScope,
    RootManagerScopeConfigurationError,
    create_deployment_root_http_module,
)
from atlanticus.web.deployment_access import (
    DeploymentAccessAuthentication,
    DeploymentAccessIdentity,
    DeploymentAccessMaterialError,
    DeploymentAccessService,
    DeploymentAccessStatus,
    DeploymentAccessStorageError,
    MaterialAvailability,
)
from atlanticus.web.identity.errors import IdentityAuthenticationError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.manager import ManagerSurface
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry


class FakeAccess(DeploymentAccessService):
    def __init__(self):
        self.fingerprint = 'a' * 64
        self.unavailable = False

    def authenticate(self, *, service_user, password):
        if (service_user, password) != ('root', 'correct-password-123'):
            raise DeploymentAccessMaterialError('Invalid credentials')
        return DeploymentAccessAuthentication(
            DeploymentAccessIdentity('b' * 32, 'root', 'app', 'local'), self.fingerprint
        )

    def inspect(self):
        if self.unavailable:
            raise DeploymentAccessStorageError('Storage unavailable')
        return DeploymentAccessStatus(MaterialAvailability.PRESENT, self.fingerprint)


class DeniedProvider(IdentityProvider):
    def __init__(self):
        self.calls = 0

    @property
    def key(self):
        return 'denied'

    @property
    def production_ready(self):
        return True

    def validate_configuration(self):
        pass

    def resolve(self, _request: Request) -> AuthenticatedIdentity:
        self.calls += 1
        raise IdentityAuthenticationError('Authentication denied')


class FakeManagerSurface(ManagerSurface):
    def __init__(self):
        item = SimpleNamespace(route='/inventory')
        self._registry = SimpleNamespace(
            root_route='/manager',
            items=(item,),
            route_for=lambda value: '/manager' + value.route,
        )

        def register_general(app, _services):
            app.callback_map['manager.content'] = {'owner': 'manager'}

        def register_entry(app, _services):
            app.callback_map['manager.entry'] = {'owner': 'entry'}

        self._web_modules = (
            WebModule(name='manager-surface', register_callbacks=register_general),
            WebModule(name='manager-entry', register_callbacks=register_entry),
        )

    @property
    def web_modules(self):
        return self._web_modules

    @property
    def registry(self):
        return self._registry

    def layout(self, _services):
        return 'MANAGER_ONLY_LAYOUT'


class FakeDash:
    def __init__(self):
        self.callback_map = {'operational.output': {'owner': 'operational'}}
        self.layout = lambda: 'OPERATIONAL_LAYOUT'


def _token(response):
    value = re.search(r'name="csrf_token" value="([\w-]+)"', response.get_data(as_text=True))
    assert value is not None
    return value.group(1)


def _create(monkeypatch, *, install_guard=True):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    access = FakeAccess()
    root = DeploymentRootSession(access=access)
    manager = FakeManagerSurface()
    scope = RootManagerRequestScope(root_session=root, manager_surface=manager)
    wrapped_modules = scope.manager_web_modules()
    guard = scope.guard_module()
    identity_provider = DeniedProvider()
    server = Flask(__name__)
    server.secret_key = 'for-tests-only-secret'
    services = ServiceRegistry()
    identity = create_identity_module(
        identity_provider,
        independent_routes=ROOT_INDEPENDENT_ROUTES,
        alternative_request_authorizer=scope.authorize,
    )
    identity.register_services(services)
    identity.register_middlewares(server, services)
    http = create_deployment_root_http_module(
        root_session=root, allow_login_attempt=lambda _ip: True
    )
    http.register_middlewares(server, services)
    guard.register_middlewares(server, services)
    http.register_routes(server, services)
    app = FakeDash()
    if install_guard:
        for module in wrapped_modules:
            if module.register_callbacks is not None:
                module.register_callbacks(app, services)
        guard.register_callbacks(app, services)

    server.add_url_rule('/manager', 'manager', lambda: 'MANAGER_INDEX')
    server.add_url_rule('/manager/inventory', 'inventory', lambda: 'INVENTORY_INDEX')
    server.add_url_rule('/manager/foreign', 'foreign', lambda: 'FOREIGN_ROUTE')
    server.add_url_rule('/operational', 'operational', lambda: 'OPERATIONAL_INDEX')
    server.add_url_rule('/api/private', 'private', lambda: 'PRIVATE_DATA')
    server.add_url_rule('/_dash-layout', 'layout', lambda: jsonify(app.layout()))
    server.add_url_rule(
        '/_dash-dependencies',
        'dependencies',
        lambda: jsonify(
            [
                {'output': 'operational.output', 'inputs': []},
                {'output': 'manager.content', 'inputs': []},
                {'output': 'manager.entry', 'inputs': []},
            ]
        ),
    )
    server.add_url_rule(
        '/_dash-update-component', 'update', lambda: 'CALLBACK_OK', methods=['POST', 'GET']
    )
    server.add_url_rule('/_dash-component-suites/library/test.js', 'script', lambda: 'SCRIPT')
    return server, access, scope, app, identity_provider, wrapped_modules, guard, services


def _login(client):
    csrf = _token(client.get(ROOT_LOGIN_PATH))
    result = client.post(
        ROOT_LOGIN_PATH,
        data={
            'csrf_token': csrf,
            'service_user': 'root',
            'password': 'correct-password-123',
        },
    )
    assert result.status_code == 303


def test_manager_exact_routes_and_root_only_layout(monkeypatch):
    server, _access, _, _, provider, *_ = _create(monkeypatch)
    client = server.test_client()
    assert client.get('/manager').status_code == 401
    assert client.get('/_dash-layout').status_code == 401
    _login(client)
    assert client.get('/manager').get_data(as_text=True) == 'MANAGER_INDEX'
    assert client.get('/manager/inventory').status_code == 200
    layout = client.get('/_dash-layout')
    assert layout.json == 'MANAGER_ONLY_LAYOUT'
    assert layout.headers['Cache-Control'] == 'private, no-store'


def test_other_endpoints_are_not_exempted_for_root(monkeypatch):
    server, *_ = _create(monkeypatch)
    client = server.test_client()
    _login(client)
    for path in ('/operational', '/api/private', '/manager/foreign', '/manager-root/other'):
        assert client.get(path).status_code == 401
    assert client.post('/manager').status_code == 401
    assert client.get('/_dash-update-component').status_code == 401
    assert client.post('/_dash-dependencies').status_code == 401
    assert client.get('/_dash-component-suites/library/test.js').status_code == 200


def test_dash_dependencies_are_filtered_and_manager_callbacks_only(monkeypatch):
    server, _access, scope, app, *_ = _create(monkeypatch)
    client = server.test_client()
    _login(client)
    dependencies = client.get('/_dash-dependencies')
    assert dependencies.status_code == 200
    assert {item['output'] for item in dependencies.json} == {'manager.content', 'manager.entry'}
    assert dependencies.headers['Cache-Control'] == 'private, no-store'
    assert app.callback_map['operational.output']['owner'] == 'operational'
    assert scope._allowed_outputs == frozenset({'manager.content', 'manager.entry'})
    for output in ('manager.content', 'manager.entry'):
        assert client.post('/_dash-update-component', json={'output': output}).status_code == 200
    for data in ({'output': 'operational.output'}, {'output': 'unknown'}, {}, []):
        assert client.post('/_dash-update-component', json=data).status_code == 401
    assert client.post('/_dash-update-component', data='{}').status_code == 401


def test_missing_session_and_rotated_material_are_denied(monkeypatch):
    server, access, *_ = _create(monkeypatch)
    client = server.test_client()
    denied = client.post('/_dash-update-component', json={'output': 'manager.content'})
    assert denied.status_code == 401
    _login(client)
    access.fingerprint = 'c' * 64
    assert client.get('/manager').status_code == 401
    assert client.get('/_dash-dependencies').status_code == 401


def test_storage_failure_fails_closed_for_manager_but_not_public_root_login(monkeypatch):
    server, access, *_ = _create(monkeypatch)
    client = server.test_client()
    _login(client)
    access.unavailable = True
    assert client.get('/manager').status_code == 503
    assert client.get('/_dash-dependencies').status_code == 503
    assert client.get(ROOT_LOGIN_PATH).status_code == 200


def test_guard_requires_callback_modules_to_be_registered_first(monkeypatch):
    server, _access, _scope, app, _provider, modules, guard, services = _create(
        monkeypatch, install_guard=False
    )
    del server
    with pytest.raises(RootManagerScopeConfigurationError, match='registered before'):
        guard.register_callbacks(app, services)
    for module in modules:
        if module.register_callbacks is not None:
            module.register_callbacks(app, services)
    guard.register_callbacks(app, services)
    with pytest.raises(RootManagerScopeConfigurationError, match='twice'):
        guard.register_callbacks(app, services)


def test_scope_cannot_be_composed_twice_or_use_invalid_contract(monkeypatch):
    _server, _access, scope, *_ = _create(monkeypatch)
    with pytest.raises(RootManagerScopeConfigurationError, match='already composed'):
        scope.manager_web_modules()
    with pytest.raises(RootManagerScopeConfigurationError, match='ManagerSurface'):
        RootManagerRequestScope(
            root_session=DeploymentRootSession(access=FakeAccess()),
            manager_surface=object(),
        )
    with pytest.raises(TypeError, match='callable'):
        create_identity_module(DeniedProvider(), alternative_request_authorizer=object())


def test_root_layout_does_not_replace_normal_layout_without_admission(monkeypatch):
    _server, _access, _scope, app, *_ = _create(monkeypatch)
    assert app.layout() == 'OPERATIONAL_LAYOUT'
