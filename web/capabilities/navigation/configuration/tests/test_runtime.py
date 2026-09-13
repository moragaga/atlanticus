from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from flask import Flask

from atlanticus.web.navigation.api import (
    NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
    NavigationDefinition,
    NavigationDefinitionProvider,
    NavigationLinkDefinition,
    NavigationPrincipal,
    NavigationPrincipalProvider,
    NavigationUser,
    create_navigation_authorization_module,
)
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
    create_projected_navigation_definition_provider,
    create_projected_navigation_module,
)
from atlanticus.web.projection.errors import ProjectionInvariantError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey, SourceReleaseId

_SOURCE_KEY = SourceKey('navigation-configuration')


def _projection(
    href: str = '/one',
    *,
    source_key: SourceKey = _SOURCE_KEY,
    release_id: str = 'source-1',
) -> ProjectionRecord[NavigationConfigurationCatalog]:
    published_at = datetime(2026, 9, 13, 0, 0, tzinfo=UTC)
    return ProjectionRecord(
        source_key=source_key,
        source_release_id=SourceReleaseId(release_id),
        source_published_at_utc=published_at,
        projected_at_utc=published_at,
        payload=NavigationConfigurationCatalog(
            links=(
                NavigationLinkConfiguration(
                    key='one',
                    label='One',
                    href=href,
                    allowed_profiles=('guest',),
                ),
            )
        ),
    )


@dataclass(slots=True)
class _MemoryProjectionStore(ProjectionStore[NavigationConfigurationCatalog]):
    active: dict[SourceKey, ProjectionRecord[NavigationConfigurationCatalog]] = field(
        default_factory=dict
    )
    get_calls: int = 0

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[NavigationConfigurationCatalog] | None:
        self.get_calls += 1
        return self.active.get(source_key)

    def replace_active(
        self,
        projection: ProjectionRecord[NavigationConfigurationCatalog],
    ) -> ProjectionRecord[NavigationConfigurationCatalog]:
        self.active[projection.source_key] = projection
        return projection


def test_projected_definition_provider_reads_active_projection() -> None:
    store = _MemoryProjectionStore(active={_SOURCE_KEY: _projection()})
    provider = create_projected_navigation_definition_provider(store, source_key=_SOURCE_KEY)

    definition = provider.current()

    assert definition.links == (
        NavigationLinkDefinition(
            key='one',
            label='One',
            href='/one',
            allowed_profiles=('guest',),
        ),
    )


def test_projected_definition_provider_observes_replaced_projection() -> None:
    store = _MemoryProjectionStore(active={_SOURCE_KEY: _projection('/one')})
    provider = create_projected_navigation_definition_provider(store, source_key=_SOURCE_KEY)

    assert provider.current().links[0].href == '/one'
    store.replace_active(_projection('/updated', release_id='source-2'))
    assert provider.current().links[0].href == '/updated'


def test_projected_definition_provider_is_empty_without_projection() -> None:
    provider = create_projected_navigation_definition_provider(
        _MemoryProjectionStore(),
        source_key=_SOURCE_KEY,
    )

    assert provider.current() == NavigationDefinition()


def test_projected_navigation_module_registers_dynamic_provider() -> None:
    store = _MemoryProjectionStore(active={_SOURCE_KEY: _projection()})
    module = create_projected_navigation_module(store, source_key=_SOURCE_KEY)
    services = ServiceRegistry()

    assert module.register_services is not None
    module.register_services(services)
    provider = services.require(
        NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
        NavigationDefinitionProvider,
    )

    assert provider.current().links[0].href == '/one'


def test_projected_navigation_updates_authorization_without_recomposing_application() -> None:
    store = _MemoryProjectionStore(active={_SOURCE_KEY: _projection('/one')})
    principal = NavigationPrincipal(
        access_key='guest',
        user=NavigationUser(
            display_name='Guest',
            profile_key='guest',
            profile_label='Guest',
            profile_background_color='#123456',
            profile_text_color='#FFFFFF',
            avatar_text='G',
        ),
    )
    navigation = create_projected_navigation_module(
        store,
        source_key=_SOURCE_KEY,
        principal_provider=NavigationPrincipalProvider(lambda: principal),
    )
    authorization = create_navigation_authorization_module()
    services = ServiceRegistry()
    assert navigation.register_services is not None
    navigation.register_services(services)
    services.freeze()
    server = Flask(__name__)
    assert authorization.register_middlewares is not None
    authorization.register_middlewares(server, services)

    @server.get('/one')
    def one():
        return 'one'

    @server.get('/updated')
    def updated():
        return 'updated'

    client = server.test_client()
    assert client.get('/one', headers={'Accept': 'text/html'}).status_code == 200
    assert client.get('/updated', headers={'Accept': 'text/html'}).status_code == 403

    store.replace_active(_projection('/updated', release_id='source-2'))

    assert client.get('/one', headers={'Accept': 'text/html'}).status_code == 403
    assert client.get('/updated', headers={'Accept': 'text/html'}).status_code == 200


def test_projected_definition_is_loaded_once_per_request() -> None:
    store = _MemoryProjectionStore(active={_SOURCE_KEY: _projection('/one')})
    provider = create_projected_navigation_definition_provider(store, source_key=_SOURCE_KEY)
    server = Flask(__name__)

    @server.get('/')
    def home():
        first = provider.current()
        second = provider.current()
        return {'same': first is second, 'href': first.links[0].href}

    first_response = server.test_client().get('/')
    store.replace_active(_projection('/updated', release_id='source-2'))
    second_response = server.test_client().get('/')

    assert first_response.get_json() == {'same': True, 'href': '/one'}
    assert second_response.get_json() == {'same': True, 'href': '/updated'}
    assert store.get_calls == 2


def test_projected_definition_provider_rejects_wrong_source_key_from_store() -> None:
    wrong = _projection(source_key=SourceKey('other-navigation'))

    class BrokenProjectionStore(_MemoryProjectionStore):
        def get_active(self, source_key: SourceKey):
            return wrong

    provider = create_projected_navigation_definition_provider(
        BrokenProjectionStore(),
        source_key=_SOURCE_KEY,
    )

    with pytest.raises(ProjectionInvariantError, match='different source key'):
        provider.current()
