from pathlib import Path

import pytest
from flask import Flask, Request

from atlanticus.web.identity.access import (
    ACCESS_RUNTIME_SERVICE_KEY,
    AccessDecision,
    AccessResolver,
    AccessRuntime,
    AccessStatus,
)
from atlanticus.web.identity.errors import (
    AccessResolverUnavailableError,
    IdentityAuthenticationError,
    IdentityConfigurationError,
    IdentityProviderUnavailableError,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.services import ServiceRegistry


class CountingProvider(IdentityProvider):
    def __init__(self, *, mode: str = 'ok', production_ready: bool = True) -> None:
        self.calls = 0
        self.mode = mode
        self._production_ready = production_ready

    @property
    def key(self) -> str:
        return 'test'

    @property
    def production_ready(self) -> bool:
        return self._production_ready

    def validate_configuration(self) -> None:
        return None

    def resolve(self, request: Request) -> AuthenticatedIdentity:
        del request
        self.calls += 1
        if self.mode == 'invalid':
            raise IdentityAuthenticationError('Invalid identity')
        if self.mode == 'unavailable':
            raise IdentityProviderUnavailableError('Provider unavailable')
        return AuthenticatedIdentity(provider_key='test', issuer='test', subject_id='subject')


class CountingResolver(AccessResolver):
    def __init__(self, *, disabled: bool = False) -> None:
        self.calls = 0
        self.disabled = disabled

    def resolve(
        self,
        identity: AuthenticatedIdentity,
        *,
        load_id: str,
    ) -> AccessDecision:
        del identity, load_id
        self.calls += 1
        if self.disabled:
            return AccessDecision(status=AccessStatus.USER_DISABLED, user_id='user-1')
        return AccessDecision(status=AccessStatus.READY, user_id=f'user-{self.calls}')


class UnavailableResolver(AccessResolver):
    def resolve(
        self,
        identity: AuthenticatedIdentity,
        *,
        load_id: str,
    ) -> AccessDecision:
        del identity, load_id
        raise AccessResolverUnavailableError('Users unavailable')


def _build_server(
    monkeypatch,
    tmp_path: Path,
    provider: IdentityProvider,
    resolver: AccessResolver,
) -> tuple[Flask, ServiceRegistry]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.setenv('ATLANTICUS_IDENTITY_PROVIDER', provider.key)
    module = create_identity_module(provider, access_resolver=resolver)
    services = ServiceRegistry()
    assert module.register_services is not None
    module.register_services(services)
    services.freeze()
    server = Flask(__name__)
    assert module.register_middlewares is not None
    module.register_middlewares(server, services)

    @server.get('/')
    def home():
        return 'home'

    @server.get('/api/snapshot')
    def snapshot():
        current = services.require(ACCESS_RUNTIME_SERVICE_KEY, AccessRuntime).current()
        return {
            'load_id': current.load_id,
            'status': current.status.value,
            'user_id': current.user_id,
        }

    @server.post('/_dash-update-component')
    def callback():
        return {'ok': True}

    @server.get('/.auth/logout')
    def logout():
        return 'logout'

    return server, services


def test_page_load_resolves_once_callbacks_reuse_and_reload_refreshes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    provider = CountingProvider()
    resolver = CountingResolver()
    server, _ = _build_server(monkeypatch, tmp_path, provider, resolver)
    client = server.test_client()

    first = client.get('/', headers={'Accept': 'text/html'})
    first_snapshot = client.get('/api/snapshot').get_json()
    callback = client.post('/_dash-update-component')
    second_snapshot = client.get('/api/snapshot').get_json()
    reload_response = client.get('/', headers={'Accept': 'text/html'})
    reloaded_snapshot = client.get('/api/snapshot').get_json()

    assert first.status_code == 200
    assert callback.status_code == 200
    assert reload_response.status_code == 200
    assert provider.calls == 2
    assert resolver.calls == 2
    assert first_snapshot == second_snapshot
    assert first_snapshot['load_id'] != reloaded_snapshot['load_id']
    assert first_snapshot['user_id'] == 'user-1'
    assert reloaded_snapshot['user_id'] == 'user-2'


def test_invalid_identity_returns_neutral_page_without_second_resolution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    provider = CountingProvider(mode='invalid')
    server, _ = _build_server(monkeypatch, tmp_path, provider, CountingResolver())

    response = server.test_client().get('/', headers={'Accept': 'text/html'})

    assert response.status_code == 401
    assert 'No fue posible iniciar sesión' in response.get_data(as_text=True)
    assert 'Reintentar' in response.get_data(as_text=True)
    assert provider.calls == 1


def test_disabled_user_returns_neutral_page(monkeypatch, tmp_path: Path) -> None:
    provider = CountingProvider()
    resolver = CountingResolver(disabled=True)
    server, _ = _build_server(monkeypatch, tmp_path, provider, resolver)

    response = server.test_client().get('/', headers={'Accept': 'text/html'})

    assert response.status_code == 403
    assert 'Usuario desactivado' in response.get_data(as_text=True)
    assert 'no tiene acceso a esta aplicación' in response.get_data(as_text=True)
    assert provider.calls == 1
    assert resolver.calls == 1


def test_provider_unavailable_is_not_reported_as_invalid_credentials(
    monkeypatch,
    tmp_path: Path,
) -> None:
    provider = CountingProvider(mode='unavailable')
    server, _ = _build_server(monkeypatch, tmp_path, provider, CountingResolver())

    response = server.test_client().get('/', headers={'Accept': 'text/html'})

    assert response.status_code == 503
    assert 'No fue posible iniciar sesión' in response.get_data(as_text=True)
    assert 'servicio de identidad no está disponible' in response.get_data(as_text=True)
    assert 'Reintentar' in response.get_data(as_text=True)


def test_rejected_access_short_circuits_later_middlewares(monkeypatch, tmp_path: Path) -> None:
    provider = CountingProvider(mode='invalid')
    server, _ = _build_server(monkeypatch, tmp_path, provider, CountingResolver())
    later_middleware_calls = 0

    @server.before_request
    def operational_middleware():
        nonlocal later_middleware_calls
        later_middleware_calls += 1
        raise AssertionError('Operational middleware must not run for rejected access')

    response = server.test_client().get('/', headers={'Accept': 'text/html'})

    assert response.status_code == 401
    assert 'No fue posible iniciar sesión' in response.get_data(as_text=True)
    assert 'Reintentar' in response.get_data(as_text=True)
    assert provider.calls == 1
    assert later_middleware_calls == 0


def test_local_session_secret_is_persisted_for_multiple_workers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    provider = CountingProvider()
    resolver = CountingResolver()
    first, _ = _build_server(monkeypatch, tmp_path, provider, resolver)
    first_secret = first.secret_key
    second, _ = _build_server(monkeypatch, tmp_path, CountingProvider(), CountingResolver())

    assert first_secret
    assert second.secret_key == first_secret
    assert (tmp_path / '.runtime' / 'identity' / 'session.key').is_file()


def test_production_accepts_any_production_ready_provider(monkeypatch) -> None:
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    monkeypatch.setenv('ATLANTICUS_IDENTITY_PROVIDER', 'test')
    module = create_identity_module(CountingProvider(production_ready=True))
    services = ServiceRegistry()

    assert module.register_services is not None
    module.register_services(services)


def test_production_rejects_local_only_provider(monkeypatch) -> None:
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    monkeypatch.setenv('ATLANTICUS_IDENTITY_PROVIDER', 'test')
    module = create_identity_module(CountingProvider(production_ready=False))
    services = ServiceRegistry()

    assert module.register_services is not None
    with pytest.raises(IdentityConfigurationError, match='not allowed in production'):
        module.register_services(services)


def test_production_requires_flask_secret_key(monkeypatch) -> None:
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    monkeypatch.setenv('ATLANTICUS_IDENTITY_PROVIDER', 'test')
    module = create_identity_module(CountingProvider(production_ready=True))
    services = ServiceRegistry()
    assert module.register_services is not None
    module.register_services(services)
    services.freeze()
    server = Flask(__name__)

    assert module.register_middlewares is not None
    with pytest.raises(IdentityConfigurationError, match='SECRET_KEY'):
        module.register_middlewares(server, services)


def test_access_resolver_unavailable_returns_service_unavailable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    server, _ = _build_server(
        monkeypatch,
        tmp_path,
        CountingProvider(),
        UnavailableResolver(),
    )

    response = server.test_client().get('/', headers={'Accept': 'text/html'})

    assert response.status_code == 503
    assert 'No fue posible iniciar sesión' in response.get_data(as_text=True)
    assert 'Reintentar' in response.get_data(as_text=True)


def test_disabled_user_short_circuits_later_middlewares(monkeypatch, tmp_path: Path) -> None:
    server, _ = _build_server(
        monkeypatch,
        tmp_path,
        CountingProvider(),
        CountingResolver(disabled=True),
    )
    later_middleware_calls = 0

    @server.before_request
    def operational_middleware():
        nonlocal later_middleware_calls
        later_middleware_calls += 1
        raise AssertionError('Operational middleware must not run for disabled users')

    response = server.test_client().get('/', headers={'Accept': 'text/html'})

    assert response.status_code == 403
    assert 'Usuario desactivado' in response.get_data(as_text=True)
    assert later_middleware_calls == 0


def test_disabled_snapshot_blocks_follow_up_api_without_second_resolution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    provider = CountingProvider()
    resolver = CountingResolver(disabled=True)
    server, _ = _build_server(monkeypatch, tmp_path, provider, resolver)
    client = server.test_client()

    page_response = client.get('/', headers={'Accept': 'text/html'})
    api_response = client.get('/api/snapshot')

    assert page_response.status_code == 403
    assert api_response.status_code == 403
    assert 'Usuario desactivado' in api_response.get_data(as_text=True)
    assert provider.calls == 1
    assert resolver.calls == 1


def test_invalid_identity_blocks_direct_api_request(monkeypatch, tmp_path: Path) -> None:
    provider = CountingProvider(mode='invalid')
    server, _ = _build_server(monkeypatch, tmp_path, provider, CountingResolver())

    response = server.test_client().get('/api/snapshot')

    assert response.status_code == 401
    assert 'No fue posible iniciar sesión' in response.get_data(as_text=True)
    assert 'Reintentar' in response.get_data(as_text=True)
    assert provider.calls == 1


def test_platform_auth_route_is_not_intercepted(monkeypatch, tmp_path: Path) -> None:
    provider = CountingProvider(mode='invalid')
    server, _ = _build_server(monkeypatch, tmp_path, provider, CountingResolver())

    response = server.test_client().get('/.auth/logout')

    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'logout'
    assert provider.calls == 0
