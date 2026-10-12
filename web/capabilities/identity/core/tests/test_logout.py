from pathlib import Path

import pytest
from flask import Flask, Request

from atlanticus.web.identity.errors import IdentityAuthenticationError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.services import ServiceRegistry


class _FailingProvider(IdentityProvider):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def key(self) -> str:
        return 'test'

    @property
    def production_ready(self) -> bool:
        return True

    def validate_configuration(self) -> None:
        pass

    def resolve(self, request: Request) -> AuthenticatedIdentity:
        del request
        self.calls += 1
        raise IdentityAuthenticationError('Invalid identity')


def _app(monkeypatch, tmp_path: Path, environment: str) -> tuple[Flask, _FailingProvider]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', environment)
    provider = _FailingProvider()
    module = create_identity_module(provider)
    services = ServiceRegistry()
    assert module.register_services is not None
    assert module.register_middlewares is not None
    assert module.register_routes is not None
    module.register_services(services)
    services.freeze()
    app = Flask(__name__)
    if environment == 'production':
        app.secret_key = 'test-only-session-secret'
    module.register_middlewares(app, services)
    module.register_routes(app, services)
    return app, provider


@pytest.mark.parametrize(
    ('environment', 'expected_location'),
    (
        ('local', '/'),
        ('production', '/.auth/logout'),
    ),
)
def test_logout_clears_flask_session_and_redirects_without_resolving_identity(
    monkeypatch, tmp_path: Path, environment: str, expected_location: str,
) -> None:
    app, provider = _app(monkeypatch, tmp_path, environment)
    client = app.test_client()
    with client.session_transaction(base_url='https://localhost') as current_session:
        current_session['example'] = 'persisted'
        current_session['access_snapshot'] = {'stale': True}

    response = client.get('/logout', base_url='https://localhost', follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['Location'] == expected_location
    assert provider.calls == 0
    with client.session_transaction(base_url='https://localhost') as current_session:
        assert dict(current_session) == {}


def test_logout_without_existing_session_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    app, provider = _app(monkeypatch, tmp_path, 'local')
    client = app.test_client()

    first = client.get('/logout')
    second = client.get('/logout')

    assert (first.status_code, second.status_code) == (302, 302)
    assert first.headers['Location'] == second.headers['Location'] == '/'
    assert provider.calls == 0


def test_logout_only_accepts_get(monkeypatch, tmp_path: Path) -> None:
    app, provider = _app(monkeypatch, tmp_path, 'local')
    response = app.test_client().post('/logout')
    assert response.status_code == 405
    assert provider.calls == 0
