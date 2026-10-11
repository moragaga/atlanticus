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


def test_new_version_changes_service_worker_script() -> None:
    first = Flask('first')
    second = Flask('second')
    register_pwa_routes(first, _definition('1.0.0'))
    register_pwa_routes(second, _definition('2.0.0'))

    first_script = first.test_client().get('/service-worker.js').get_data(as_text=True)
    second_script = second.test_client().get('/service-worker.js').get_data(as_text=True)

    assert first_script != second_script
