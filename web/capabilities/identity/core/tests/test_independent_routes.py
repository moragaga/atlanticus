from __future__ import annotations

import pytest
from flask import Flask, Request

from atlanticus.web.identity.errors import IdentityAuthenticationError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.services import ServiceRegistry


class DeniedProvider(IdentityProvider):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def key(self) -> str:
        return 'denied'

    @property
    def production_ready(self) -> bool:
        return True

    def validate_configuration(self) -> None:
        pass

    def resolve(self, request: Request) -> AuthenticatedIdentity:
        self.calls += 1
        raise IdentityAuthenticationError('Denied')


def test_independent_route_is_excluded_without_exempting_nearby_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    provider = DeniedProvider()
    module = create_identity_module(
        provider, independent_routes=('/maintenance-console', '/maintenance-console/logout')
    )
    services = ServiceRegistry()
    module.register_services(services)
    server = Flask(__name__)
    module.register_middlewares(server, services)
    server.add_url_rule('/maintenance-console', 'maintenance', lambda: 'maintenance')
    server.add_url_rule('/maintenance-console/logout', 'logout', lambda: 'logout')
    server.add_url_rule('/maintenance-console/unknown', 'unknown', lambda: 'unknown')
    server.add_url_rule('/manager', 'manager', lambda: 'manager')
    client = server.test_client()
    assert client.get('/maintenance-console').get_data(as_text=True) == 'maintenance'
    assert client.get('/maintenance-console/logout').get_data(as_text=True) == 'logout'
    assert provider.calls == 0
    assert client.get('/maintenance-console/unknown').status_code == 401
    assert provider.calls == 1
    assert client.get('/manager').status_code == 401
    assert provider.calls == 1
    isolated_client = server.test_client()
    assert isolated_client.get('/manager').status_code == 401
    assert provider.calls == 2


@pytest.mark.parametrize('route', ['', 'maintenance-console', '/', '/health/',
                                   '/maintenance-console/', '/maintenance-console//x'])
def test_independent_routes_reject_invalid_or_public_paths(route):
    with pytest.raises(ValueError, match='Independent route'):
        create_identity_module(DeniedProvider(), independent_routes=(route,))
