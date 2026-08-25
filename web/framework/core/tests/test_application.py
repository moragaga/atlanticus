from pathlib import Path

import pytest
from dash import html, page_container, page_registry

from atlanticus.web.application import create_web_application
from atlanticus.web.assets import AssetLayer
from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.health import HealthRegistry
from atlanticus.web.index import IndexContribution
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry


def _build_layer(tmp_path: Path) -> AssetLayer:
    root = tmp_path / 'layer' / 'resources'
    (root / 'css').mkdir(parents=True)
    (root / 'js').mkdir(parents=True)
    (root / 'css' / 'base.css').write_text('body {}', encoding='utf-8')
    (root / 'css' / 'css.list').write_text('base.css\n', encoding='utf-8')
    (root / 'js' / 'base.js').write_text('window.test=true;', encoding='utf-8')
    (root / 'js' / 'js.list').write_text('base.js\n', encoding='utf-8')
    return AssetLayer(name='test', load_order=100, source_directory=tmp_path / 'layer')


def _build_page_package(tmp_path: Path, package_name: str = 'test_web_pages') -> str:
    package = tmp_path / package_name
    package.mkdir()
    (package / '__init__.py').write_text('', encoding='utf-8')
    (package / '_private.py').write_text(
        "raise RuntimeError('must not import')\n",
        encoding='utf-8',
    )
    (package / 'home.py').write_text(
        'from dash import html, register_page\n'
        "register_page(__name__, path='/', name='Home', order=0)\n"
        "layout = html.Div('Home')\n",
        encoding='utf-8',
    )
    (package / 'status.py').write_text(
        'from dash import html, register_page\n'
        "register_page(__name__, path='/status', name='Status', order=1)\n"
        "layout = html.Div('Status')\n",
        encoding='utf-8',
    )
    return package_name


def _build_namespaced_application_package(tmp_path: Path) -> tuple[str, Path]:
    package = tmp_path / 'test_namespace' / 'applications' / 'reference'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('', encoding='utf-8')
    return 'test_namespace.applications.reference', package


def test_application_composes_pages_services_middlewares_routes_and_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_name = _build_page_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    def register_services(services: ServiceRegistry) -> None:
        services.add('test.message', 'ok')

    def register_health(health: HealthRegistry, services: ServiceRegistry) -> None:
        health.add('test', lambda: services.require('test.message', str) == 'ok')

    def register_middlewares(server, _services: ServiceRegistry) -> None:
        @server.after_request
        def add_header(response):
            response.headers['X-Test-Middleware'] = 'active'
            return response

    def register_routes(server, services: ServiceRegistry) -> None:
        @server.get('/api/test')
        def api_test():
            return {'message': services.require('test.message', str)}, 200

    module = WebModule(
        name='test',
        page_packages=(package_name,),
        register_services=register_services,
        register_health_checks=register_health,
        register_middlewares=register_middlewares,
        register_routes=register_routes,
        index=IndexContribution(runtime_config={'enabled': True}),
    )

    runtime = create_web_application(
        WebApplicationDefinition(
            import_name='test_web',
            metadata=ApplicationMetadata(
                application_id='test-web',
                display_name='Test Web',
                version='0.1.0',
            ),
            publications_root=tmp_path / 'published',
            layout=lambda services: html.Main(
                [html.Div(services.require('test.message', str)), page_container]
            ),
            modules=(module,),
            asset_layers=(_build_layer(tmp_path),),
        ),
    )

    client = runtime.server.test_client()
    live = client.get('/health/live')
    ready = client.get('/health/ready')
    api = client.get('/api/test')

    assert live.status_code == 200
    assert live.get_json()['environment'] == 'local'
    assert ready.status_code == 200
    assert ready.get_json()['checks']['test'] == {'status': 'healthy'}
    assert api.get_json() == {'message': 'ok'}
    assert api.headers['X-Test-Middleware'] == 'active'
    assert runtime.services.frozen is True
    assert runtime.page_modules == ('test_web_pages.home', 'test_web_pages.status')
    assert 'test_web_pages.home' in page_registry
    assert page_registry['test_web_pages.home']['layout'] is not None
    assert 'test_web_pages.status' in page_registry
    assert page_registry['test_web_pages.status']['layout'] is not None
    assert '"test":{"enabled":true}' in runtime.dash.index_string


def test_public_infrastructure_requests_defer_dash_layout_initialization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_name = _build_page_package(tmp_path, 'test_deferred_layout_pages')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    layout_calls = 0

    def layout(_services: ServiceRegistry):
        nonlocal layout_calls
        layout_calls += 1
        return html.Main([html.Div('Deferred layout'), page_container])

    runtime = create_web_application(
        WebApplicationDefinition(
            import_name='test_web_deferred_layout',
            metadata=ApplicationMetadata(
                application_id='test-web-deferred-layout',
                display_name='Deferred Layout',
                version='0.1.0',
            ),
            publications_root=tmp_path / 'published-deferred-layout',
            layout=layout,
            modules=(WebModule(name='deferred-layout'),),
            page_packages=(package_name,),
        )
    )

    client = runtime.server.test_client()
    assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').status_code == 200
    assert layout_calls == 0

    assert client.get('/_dash-layout').status_code == 200
    assert layout_calls > 0


def test_application_requires_pages(tmp_path: Path) -> None:
    with pytest.raises(WebDefinitionError, match='at least one page package'):
        create_web_application(
            WebApplicationDefinition(
                import_name='test_web_empty',
                metadata=ApplicationMetadata(
                    application_id='test-web-empty',
                    display_name='Test Web',
                    version='0.1.0',
                ),
                publications_root=tmp_path / 'published',
                layout=lambda _services: html.Div(),
                asset_layers=(_build_layer(tmp_path),),
            ),
        )


def test_application_supports_concrete_package_below_namespace_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import_name, package_path = _build_namespaced_application_package(tmp_path)
    page_package = _build_page_package(tmp_path, 'test_namespace_pages')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    runtime = create_web_application(
        WebApplicationDefinition(
            import_name=import_name,
            metadata=ApplicationMetadata(
                application_id='test-namespace-web',
                display_name='Test Namespace Web',
                version='0.1.0',
            ),
            publications_root=tmp_path / 'published',
            layout=lambda _services: html.Main(page_container),
            page_packages=(page_package,),
            asset_layers=(_build_layer(tmp_path),),
        ),
    )

    assert Path(runtime.server.root_path) == package_path.resolve()
    assert Path(runtime.server.instance_path) == package_path.resolve().parent / 'instance'


def test_application_optimizes_published_assets_in_production(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_name = _build_page_package(tmp_path, 'test_production_pages')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')

    runtime = create_web_application(
        WebApplicationDefinition(
            import_name='test_production_web',
            metadata=ApplicationMetadata(
                application_id='test-production-web',
                display_name='Test Production Web',
                version='0.1.0',
            ),
            publications_root=tmp_path / 'published',
            layout=lambda _services: html.Main(page_container),
            page_packages=(package_name,),
            asset_layers=(_build_layer(tmp_path),),
        ),
    )

    assert runtime.assets.css_entries == ('app.min.css',)
    assert (runtime.assets.assets_root / 'app.min.css').is_file()
    assert runtime.assets.js_entries
    assert all(
        (runtime.assets.assets_root / entry).is_file() for entry in runtime.assets.js_entries
    )
