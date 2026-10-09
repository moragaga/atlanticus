from __future__ import annotations

import re

import pytest
from flask import Flask, Request

from atlanticus.web.compositions.deployment_access_manager import (
    ROOT_INDEPENDENT_ROUTES,
    ROOT_LOGIN_PATH,
    ROOT_LOGOUT_PATH,
    ROOT_STATUS_PATH,
    DeploymentRootHttpConfigurationError,
    DeploymentRootSession,
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
from atlanticus.web.services import ServiceRegistry


class FakeAccess(DeploymentAccessService):
    def __init__(self):
        self.fingerprint = 'c' * 64
        self.availability = MaterialAvailability.PRESENT
        self.fail = False
        self.unavailable = False
        self.attempts = 0

    def authenticate(self, *, service_user, password):
        self.attempts += 1
        if self.unavailable:
            raise DeploymentAccessStorageError('Storage is not available')
        if self.fail or (service_user, password) != ('root', 'correct-password-123'):
            raise DeploymentAccessMaterialError('Invalid credentials')
        return DeploymentAccessAuthentication(
            DeploymentAccessIdentity('f' * 32, 'root', 'test', 'local'), self.fingerprint
        )

    def inspect(self):
        if self.unavailable:
            raise DeploymentAccessStorageError('Storage is not available')
        return DeploymentAccessStatus(
            self.availability,
            self.fingerprint if self.availability is MaterialAvailability.PRESENT else None,
        )


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
        return None

    def resolve(self, _request: Request) -> AuthenticatedIdentity:
        self.calls += 1
        raise IdentityAuthenticationError('Authentication denied')


def _token(response):
    match = re.search(r'name="csrf_token" value="([\w-]+)"', response.get_data(as_text=True))
    assert match is not None
    return match.group(1)


def _build(*, gate=None, with_identity=False):
    access = FakeAccess()
    root = DeploymentRootSession(access=access)
    limiter_calls = []

    def allowed(remote_address):
        limiter_calls.append(remote_address)
        return True if gate is None else gate(remote_address)

    app = Flask(__name__)
    app.secret_key = 'local-secret-for-test-only'
    services = ServiceRegistry()
    module = create_deployment_root_http_module(root_session=root, allow_login_attempt=allowed)
    module.register_middlewares(app, services)
    provider = None
    if with_identity:
        provider = DeniedProvider()
        identity = create_identity_module(provider, independent_routes=ROOT_INDEPENDENT_ROUTES)
        identity.register_services(services)
        identity.register_middlewares(app, services)
    module.register_routes(app, services)

    @app.get('/manager')
    def manager():
        return 'manager'

    @app.post('/_dash-update-component')
    def global_dash_callback():
        return 'callback'

    @app.get('/manager-root/other')
    def other():
        return 'other'

    return app, root, access, limiter_calls, provider


def _credentials(token):
    return {
        'csrf_token': token,
        'service_user': 'root',
        'password': 'correct-password-123',
    }


def test_login_status_logout_and_security_headers(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app, root, access, attempts, _ = _build()
    client = app.test_client()
    assert client.get(ROOT_STATUS_PATH).status_code == 401
    login = client.get(ROOT_LOGIN_PATH)
    assert login.status_code == 200
    assert login.headers['Cache-Control'].startswith('no-store')
    assert login.headers['X-Frame-Options'] == 'DENY'
    assert "default-src 'none'" in login.headers['Content-Security-Policy']
    assert 'secret' not in login.get_data(as_text=True).lower()
    response = client.post(ROOT_LOGIN_PATH, data=_credentials(_token(login)))
    assert response.status_code == 303
    assert response.headers['Location'] == ROOT_STATUS_PATH
    assert 'correct-password-123' not in str(response.headers)
    assert attempts == ['127.0.0.1']
    assert access.attempts == 1
    status = client.get(ROOT_STATUS_PATH)
    assert status.status_code == 200
    assert 'Sesión ROOT activa' in status.get_data(as_text=True)
    assert access.fingerprint not in status.get_data(as_text=True)
    assert client.get(ROOT_LOGOUT_PATH).status_code == 405
    invalid = client.post(ROOT_LOGOUT_PATH, data={'csrf_token': 'invalid'})
    assert invalid.status_code == 400
    assert client.get(ROOT_STATUS_PATH).status_code == 200
    logout = client.post(ROOT_LOGOUT_PATH, data={'csrf_token': _token(status)})
    assert logout.status_code == 303
    assert logout.headers['Location'] == ROOT_LOGIN_PATH
    assert client.get(ROOT_STATUS_PATH).status_code == 401


def test_csrf_required_even_with_correct_credentials(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app, _root, access, calls, _ = _build()
    client = app.test_client()
    response = client.post(ROOT_LOGIN_PATH, data=_credentials('bad'))
    assert response.status_code == 400
    token = _token(client.get(ROOT_LOGIN_PATH))
    data = _credentials(token)
    assert client.post(ROOT_LOGIN_PATH, data={**data, 'csrf_token': 'wrong'}).status_code == 400
    duplicate = {**data, 'csrf_token': [token, token]}
    assert client.post(ROOT_LOGIN_PATH, data=duplicate).status_code == 400
    assert access.attempts == 0
    assert calls == []


def test_wrong_password_invalidates_prior_root_claim(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app, _root, access, _, _ = _build()
    client = app.test_client()
    token = _token(client.get(ROOT_LOGIN_PATH))
    assert client.post(ROOT_LOGIN_PATH, data=_credentials(token)).status_code == 303
    assert client.get(ROOT_STATUS_PATH).status_code == 200
    credential = _credentials(_token(client.get(ROOT_STATUS_PATH)))
    credential['password'] = 'bad-password-123456'
    failed = client.post(ROOT_LOGIN_PATH, data=credential)
    assert failed.status_code == 401
    assert 'Invalid credentials' not in failed.get_data(as_text=True)
    assert client.get(ROOT_STATUS_PATH).status_code == 401
    assert access.attempts == 2


def test_limiter_denies_before_touching_material(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app, _root, access, calls, _ = _build(gate=lambda _: False)
    client = app.test_client()
    token = _token(client.get(ROOT_LOGIN_PATH))
    assert client.post(ROOT_LOGIN_PATH, data=_credentials(token)).status_code == 429
    assert calls == ['127.0.0.1']
    assert access.attempts == 0


def test_limiter_unavailable_fails_closed(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')

    def broken(_):
        raise RuntimeError('Limiter failed')

    app, _root, access, _, _ = _build(gate=broken)
    client = app.test_client()
    token = _token(client.get(ROOT_LOGIN_PATH))
    assert client.post(ROOT_LOGIN_PATH, data=_credentials(token)).status_code == 503
    assert access.attempts == 0


def test_backup_material_unavailable_does_not_authorize(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app, _root, access, _, _ = _build()
    client = app.test_client()
    access.unavailable = True
    token = _token(client.get(ROOT_LOGIN_PATH))
    assert client.post(ROOT_LOGIN_PATH, data=_credentials(token)).status_code == 503
    assert client.get(ROOT_STATUS_PATH).status_code == 401
    access.unavailable = False
    token = _token(client.get(ROOT_LOGIN_PATH))
    assert client.post(ROOT_LOGIN_PATH, data=_credentials(token)).status_code == 303
    access.fingerprint = 'd' * 64
    assert client.get(ROOT_STATUS_PATH).status_code == 401


def test_root_logout_does_not_clear_other_flask_session(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app, _root, _, _, _ = _build()
    client = app.test_client()
    with client.session_transaction() as values:
        values['regular-identity'] = 'untouched'
    token = _token(client.get(ROOT_LOGIN_PATH))
    assert client.post(ROOT_LOGIN_PATH, data=_credentials(token)).status_code == 303
    status = client.get(ROOT_STATUS_PATH)
    assert client.post(ROOT_LOGOUT_PATH, data={'csrf_token': _token(status)}).status_code == 303
    with client.session_transaction() as values:
        assert values['regular-identity'] == 'untouched'


def test_oversized_and_wrong_content_type_rejected_before_authentication(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app, _root, access, _, _ = _build()
    client = app.test_client()
    token = _token(client.get(ROOT_LOGIN_PATH))
    oversized = client.post(ROOT_LOGIN_PATH, data={**_credentials(token), 'password': 'x' * 10000})
    assert oversized.status_code == 413
    wrong_type = client.post(
        ROOT_LOGIN_PATH, data=_credentials(token), content_type='multipart/form-data'
    )
    assert wrong_type.status_code in (400, 415)
    assert access.attempts == 0


def test_independent_identity_routes_do_not_exempt_manager_or_dash(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app, _, access, _, provider = _build(with_identity=True)
    client = app.test_client()
    token = _token(client.get(ROOT_LOGIN_PATH))
    assert client.post(ROOT_LOGIN_PATH, data=_credentials(token)).status_code == 303
    assert client.get(ROOT_STATUS_PATH).status_code == 200
    assert provider.calls == 0
    assert access.attempts == 1
    assert client.get('/manager').status_code == 401
    assert client.post('/_dash-update-component', json={'output': 'anything'}).status_code == 401
    assert client.get('/manager-root/other').status_code == 401
    assert provider.calls >= 1


def test_no_cross_browser_session_leak(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app, _, _, _, _ = _build()
    authorized = app.test_client()
    guest = app.test_client()
    token = _token(authorized.get(ROOT_LOGIN_PATH))
    assert authorized.post(ROOT_LOGIN_PATH, data=_credentials(token)).status_code == 303
    assert authorized.get(ROOT_STATUS_PATH).status_code == 200
    assert guest.get(ROOT_STATUS_PATH).status_code == 401


def test_missing_gate_is_a_configuration_error(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    root = DeploymentRootSession(access=FakeAccess())
    with pytest.raises(DeploymentRootHttpConfigurationError):
        create_deployment_root_http_module(root_session=root, allow_login_attempt=None)
    with pytest.raises(DeploymentRootHttpConfigurationError):
        create_deployment_root_http_module(
            root_session=object(), allow_login_attempt=lambda _: True
        )
