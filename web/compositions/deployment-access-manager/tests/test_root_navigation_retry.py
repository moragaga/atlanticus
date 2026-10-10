from __future__ import annotations

import re

import pytest
from flask import Flask

from atlanticus.web.compositions.deployment_access_manager import (
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
    MaterialAvailability,
)
from atlanticus.web.services import ServiceRegistry


class ExampleAccess(DeploymentAccessService):
    def __init__(self) -> None:
        pass

    def authenticate(self, *, service_user, password):
        if (service_user, password) != ('demo', 'valid-password-12345'):
            raise DeploymentAccessMaterialError('Invalid credentials')
        return DeploymentAccessAuthentication(
            DeploymentAccessIdentity('f' * 32, 'demo', 'qualification', 'local'), 'a' * 64
        )

    def inspect(self):
        return DeploymentAccessStatus(MaterialAvailability.PRESENT, 'a' * 64)


def _token(page):
    match = re.search(r'name="csrf_token" value="([\w-]+)"', page.get_data(as_text=True))
    assert match is not None
    return match.group(1)


def test_failed_login_offers_retry_and_success_has_manager_link(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    root = DeploymentRootSession(access=ExampleAccess())
    server = Flask(__name__)
    server.secret_key = 'qualification-testing-only'
    module = create_deployment_root_http_module(
        root_session=root,
        allow_login_attempt=lambda _ip: True,
        manager_href='/manager',
    )
    services = ServiceRegistry()
    module.register_middlewares(server, services)
    module.register_routes(server, services)
    client = server.test_client()

    token = _token(client.get('/manager-root/login'))
    for _ in range(4):
        denied = client.post(
            '/manager-root/login',
            data={'csrf_token': token, 'service_user': 'demo', 'password': 'wrong-password-12345'},
        )
        assert denied.status_code == 401
        assert 'Credenciales ROOT inválidas.' in denied.get_data(as_text=True)
        assert 'name="password"' in denied.get_data(as_text=True)
        token = _token(denied)

    logged = client.post(
        '/manager-root/login',
        data={'csrf_token': token, 'service_user': 'demo', 'password': 'valid-password-12345'},
    )
    assert logged.status_code == 303
    status = client.get('/manager-root/status')
    assert status.status_code == 200
    body = status.get_data(as_text=True)
    assert '<a href="/manager">Ir al Manager</a>' in body
    assert 'Vence:' in body
    assert 'name="csrf_token"' in body
    assert 'valid-password-12345' not in body


def test_manager_link_configuration_rejects_external_paths(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    root = DeploymentRootSession(access=ExampleAccess())
    for route in ('https://evil.example', '//evil.example', '/manager?q=1', '/manager/'):
        with pytest.raises(DeploymentRootHttpConfigurationError):
            create_deployment_root_http_module(
                root_session=root, allow_login_attempt=lambda _ip: True, manager_href=route
            )
