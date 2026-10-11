from dataclasses import replace

from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.descriptor import GENERIC_APPLICATION_DESCRIPTOR
from atlanticus.web.application import create_web_application


def test_generic_pwa_routes_and_icons_are_served(tmp_path):
    descriptor = replace(GENERIC_APPLICATION_DESCRIPTOR, application_root=tmp_path)
    runtime = create_web_application(create_application_definition(application_descriptor=descriptor))
    client = runtime.server.test_client()

    manifest_response = client.get('/manifest.webmanifest')
    assert manifest_response.status_code == 200
    manifest = manifest_response.get_json()
    assert manifest['id'] == 'ada-generic-application'
    assert manifest['name'] == 'ADA'
    assert manifest['short_name'] == 'ADA'
    assert manifest['start_url'] == '/'
    assert manifest['scope'] == '/'
    assert manifest['display'] == 'standalone'
    assert len(manifest['icons']) == 3
    assert {icon['sizes'] for icon in manifest['icons']} == {'192x192', '512x512'}
    assert any(icon['purpose'] == 'maskable' for icon in manifest['icons'])

    for icon in manifest['icons']:
        response = client.get(icon['src'])
        assert response.status_code == 200
        assert response.mimetype == 'image/png'
        assert response.data.startswith(b'\x89PNG\r\n\x1a\n')

    sw = client.get('/service-worker.js')
    assert sw.status_code == 200
    assert sw.headers['Service-Worker-Allowed'] == '/'
    assert 'no-store' in sw.headers['Cache-Control']


def test_specialized_descriptor_keeps_distinct_pwa_identity(tmp_path):
    descriptor = replace(
        GENERIC_APPLICATION_DESCRIPTOR,
        application_id='ada-integrated-operations-application',
        display_name='ADA Operaciones Integradas',
        pwa_short_name='ADA Operaciones',
        application_root=tmp_path,
    )
    runtime = create_web_application(create_application_definition(application_descriptor=descriptor))
    manifest = runtime.server.test_client().get('/manifest.webmanifest').get_json()
    assert manifest['id'] == 'ada-integrated-operations-application'
    assert manifest['name'] == 'ADA Operaciones Integradas'
    assert manifest['short_name'] == 'ADA Operaciones'
    assert manifest['start_url'] == '/'
    assert manifest['scope'] == '/'
