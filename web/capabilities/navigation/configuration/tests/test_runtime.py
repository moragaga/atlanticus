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
    NavigationConfigurationProjection,
    NavigationLinkConfiguration,
    create_projected_navigation_definition_provider,
    create_projected_navigation_module,
)
from atlanticus.web.navigation.configuration.adapters.memory import (
    MemoryNavigationProjectionRepository,
)
from atlanticus.web.services import ServiceRegistry


def _projection(href: str = '/one') -> NavigationConfigurationProjection:
    return NavigationConfigurationProjection.create(
        source_revision='source-1',
        projected_by='tester',
        catalog=NavigationConfigurationCatalog(
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


def test_projected_definition_provider_reads_active_projection() -> None:
    repository = MemoryNavigationProjectionRepository(projection=_projection())
    provider = create_projected_navigation_definition_provider(repository)

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
    repository = MemoryNavigationProjectionRepository(projection=_projection('/one'))
    provider = create_projected_navigation_definition_provider(repository)

    assert provider.current().links[0].href == '/one'
    repository.projection = _projection('/updated')
    assert provider.current().links[0].href == '/updated'


def test_projected_definition_provider_is_empty_without_projection() -> None:
    provider = create_projected_navigation_definition_provider(
        MemoryNavigationProjectionRepository()
    )

    assert provider.current() == NavigationDefinition()


def test_projected_navigation_module_registers_dynamic_provider() -> None:
    repository = MemoryNavigationProjectionRepository(projection=_projection())
    module = create_projected_navigation_module(repository)
    services = ServiceRegistry()

    assert module.register_services is not None
    module.register_services(services)
    provider = services.require(
        NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
        NavigationDefinitionProvider,
    )

    assert provider.current().links[0].href == '/one'


def test_projected_navigation_updates_authorization_without_recomposing_application() -> None:
    repository = MemoryNavigationProjectionRepository(projection=_projection('/one'))
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
        repository,
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

    repository.projection = _projection('/updated')

    assert client.get('/one', headers={'Accept': 'text/html'}).status_code == 403
    assert client.get('/updated', headers={'Accept': 'text/html'}).status_code == 200


def test_projected_definition_is_loaded_once_per_request() -> None:
    class CountingRepository:
        def __init__(self) -> None:
            self.projection = _projection('/one')
            self.load_calls = 0

        def load(self):
            self.load_calls += 1
            return self.projection

    repository = CountingRepository()
    provider = create_projected_navigation_definition_provider(repository)
    server = Flask(__name__)

    @server.get('/')
    def home():
        first = provider.current()
        second = provider.current()
        return {'same': first is second, 'href': first.links[0].href}

    first_response = server.test_client().get('/')
    repository.projection = _projection('/updated')
    second_response = server.test_client().get('/')

    assert first_response.get_json() == {'same': True, 'href': '/one'}
    assert second_response.get_json() == {'same': True, 'href': '/updated'}
    assert repository.load_calls == 2
