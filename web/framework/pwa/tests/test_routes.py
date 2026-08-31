from flask import Flask

from atlanticus.web.pwa import WebPwaDefinition, register_pwa_routes


def _definition(version: str = '1.2.3') -> WebPwaDefinition:
    return WebPwaDefinition(
        application_id='generic-app',
        version=version,
        name='Generic App',
        short_name='Generic',
        theme_color='#112233',
        background_color='#FFFFFF',
    )


def test_manifest_is_generated_and_never_http_cached() -> None:
    app = Flask(__name__)
    register_pwa_routes(app, _definition())

    response = app.test_client().get('/manifest.webmanifest')

    assert response.status_code == 200
    assert response.mimetype == 'application/manifest+json'
    assert response.get_json() == {
        'id': 'generic-app',
        'name': 'Generic App',
        'short_name': 'Generic',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'theme_color': '#112233',
        'background_color': '#FFFFFF',
    }
    assert response.headers['Cache-Control'] == 'no-store, no-cache, must-revalidate, max-age=0'


def test_service_worker_is_versioned_and_scoped_to_root() -> None:
    app = Flask(__name__)
    register_pwa_routes(app, _definition('2.0.0'))

    response = app.test_client().get('/service-worker.js')
    content = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == 'application/javascript'
    assert response.headers['Service-Worker-Allowed'] == '/'
    assert response.headers['Cache-Control'] == 'no-store, no-cache, must-revalidate, max-age=0'
    assert 'atlanticus-pwa:generic-app:2.0.0' in content
    assert "url.pathname.startsWith('/assets/')" in content
    assert 'url.origin === self.location.origin' in content
    assert "CACHE_PREFIX = 'atlanticus-pwa:'" in content
    assert '/_dash-' not in content
    assert '/api/' not in content
