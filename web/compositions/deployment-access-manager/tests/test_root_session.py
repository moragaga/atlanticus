from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask, session

from atlanticus.web.compositions.deployment_access_manager import (
    DeploymentRootSession,
    DeploymentRootSessionError,
    compose_root_manager_principal,
)
from atlanticus.web.deployment_access import (
    DeploymentAccessAuthentication,
    DeploymentAccessIdentity,
    DeploymentAccessMaterialError,
    DeploymentAccessService,
    DeploymentAccessStatus,
    MaterialAvailability,
)
from atlanticus.web.manager import ManagerPrincipal


class FakeAccess(DeploymentAccessService):
    def __init__(self):
        self.fingerprint = 'a' * 64
        self.status = MaterialAvailability.PRESENT
        self.fail = False
        self.calls = 0

    def authenticate(self, *, service_user, password):
        self.calls += 1
        if self.fail or (service_user, password) != ('root', 'correct-password-123'):
            raise DeploymentAccessMaterialError('Invalid deployment access credentials')
        return DeploymentAccessAuthentication(
            identity=DeploymentAccessIdentity('b' * 32, 'root', 'test', 'local'),
            fingerprint=self.fingerprint,
        )

    def inspect(self):
        return DeploymentAccessStatus(
            self.status,
            self.fingerprint if self.status is MaterialAvailability.PRESENT else None,
        )


@pytest.fixture
def server():
    app = Flask(__name__)
    app.secret_key = 'development-session-key'
    return app


def test_login_creates_root_claim_without_credentials_and_authorizes_all_entries(server):
    access = FakeAccess()
    root = DeploymentRootSession(access=access)
    fallback_called = []

    def fallback():
        fallback_called.append(True)
        return ManagerPrincipal(subject_id='regular', display_name='Regular')

    provider = compose_root_manager_principal(root_session=root, fallback=fallback)
    with server.test_request_context('/'):
        session['regular_key'] = 'untouched'
        assert provider().administrative_override is False
        root.login(service_user='root', password='correct-password-123')
        principal = provider()
        assert principal.administrative_override is True
        assert principal.subject_id == 'deployment-root:' + 'b' * 32
        assert principal.is_local is False
        assert session['regular_key'] == 'untouched'
        assert 'correct-password-123' not in str(session)
        assert fallback_called == [True]


def test_password_failure_clears_existing_root_session(server):
    access = FakeAccess()
    root = DeploymentRootSession(access=access)
    with server.test_request_context('/'):
        root.login(service_user='root', password='correct-password-123')
        with pytest.raises(DeploymentAccessMaterialError):
            root.login(service_user='root', password='wrong-password-123')
        assert root.current() is None


def test_material_rotation_and_absence_revoke_session(server):
    access = FakeAccess()
    root = DeploymentRootSession(access=access)
    with server.test_request_context('/'):
        root.login(service_user='root', password='correct-password-123')
        access.fingerprint = 'c' * 64
        assert root.current() is None
        access.fingerprint = 'a' * 64
        root.login(service_user='root', password='correct-password-123')
        access.status = MaterialAvailability.UNAVAILABLE
        assert root.current() is None


def test_expiration_and_invalid_claims_are_rejected(server):
    access = FakeAccess()
    time = [datetime(2026, 10, 9, tzinfo=UTC)]
    root = DeploymentRootSession(access=access, ttl_seconds=30, clock=lambda: time[0])
    with server.test_request_context('/'):
        root.login(service_user='root', password='correct-password-123')
        assert root.current() is not None
        time[0] += timedelta(seconds=31)
        assert root.current() is None
        session['_atlanticus_deployment_root_manager_v1'] = {
            'material_id': 'fake',
            'service_user': 'root',
            'fingerprint': 'x' * 64,
            'issued_at_epoch': True,
            'expires_at_epoch': 999999999,
        }
        assert root.current() is None


def test_root_logout_does_not_clear_identity_session(server):
    root = DeploymentRootSession(access=FakeAccess())
    with server.test_request_context('/'):
        session['identity-session'] = 'regular'
        root.login(service_user='root', password='correct-password-123')
        root.logout()
        assert root.current() is None
        assert session['identity-session'] == 'regular'


def test_missing_flask_key_and_request_context_fail_closed(server):
    root = DeploymentRootSession(access=FakeAccess())
    with pytest.raises(DeploymentRootSessionError):
        root.current()
    server.secret_key = None
    with (
        server.test_request_context('/'),
        pytest.raises(DeploymentRootSessionError, match='secret key'),
    ):
        root.login(service_user='root', password='correct-password-123')


def test_invalid_config_is_rejected():
    access = FakeAccess()
    for value in (0, -1, 86401, True, 3.4):
        with pytest.raises(ValueError):
            DeploymentRootSession(access=access, ttl_seconds=value)
    with pytest.raises(TypeError):
        compose_root_manager_principal(root_session=object(), fallback=lambda: None)
    with pytest.raises(TypeError):
        compose_root_manager_principal(
            root_session=DeploymentRootSession(access=access), fallback=None
        )


def test_access_unavailable_at_login_does_not_issue_root_claim(server):
    access = FakeAccess()
    root = DeploymentRootSession(access=access)
    with server.test_request_context('/'):
        access.status = MaterialAvailability.UNAVAILABLE
        with pytest.raises(DeploymentRootSessionError, match='changed'):
            root.login(service_user='root', password='correct-password-123')
        assert root.current() is None


def test_fallback_is_only_called_without_root_session(server):
    root = DeploymentRootSession(access=FakeAccess())
    provider = compose_root_manager_principal(
        root_session=root,
        fallback=lambda: ManagerPrincipal(subject_id='managed', display_name='Managed'),
    )
    with server.test_request_context('/'):
        assert provider().subject_id == 'managed'
        root.login(service_user='root', password='correct-password-123')
        assert provider().subject_id.startswith('deployment-root:')
        root.logout()
        assert provider().subject_id == 'managed'


def test_signed_cookie_survives_new_request_and_isolated_clients_do_not_inherit_it(server):
    root = DeploymentRootSession(access=FakeAccess())

    @server.post('/root-login')
    def login_view():
        root.login(service_user='root', password='correct-password-123')
        return 'ok'

    @server.get('/root-principal')
    def principal_view():
        identity = root.current()
        return identity.material_id if identity is not None else 'anonymous'

    first = server.test_client()
    assert first.get('/root-principal').get_data(as_text=True) == 'anonymous'
    assert first.post('/root-login').status_code == 200
    assert first.get('/root-principal').get_data(as_text=True) == 'b' * 32
    assert server.test_client().get('/root-principal').get_data(as_text=True) == 'anonymous'


def test_root_provider_does_not_require_users_runtime_when_session_is_valid(server):
    root = DeploymentRootSession(access=FakeAccess())

    def unavailable_users_runtime():
        raise RuntimeError('Users runtime must not be accessed for a valid ROOT session')

    provider = compose_root_manager_principal(root_session=root, fallback=unavailable_users_runtime)
    with server.test_request_context('/'):
        root.login(service_user='root', password='correct-password-123')
        assert provider().administrative_override is True
        root.logout()
        with pytest.raises(RuntimeError, match='Users runtime'):
            provider()
