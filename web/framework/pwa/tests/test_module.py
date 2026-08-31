from pathlib import Path

from atlanticus.web.pwa import WebPwaDefinition, create_web_pwa_module


def test_module_contributes_manifest_metadata_and_registration_asset() -> None:
    module = create_web_pwa_module(
        WebPwaDefinition(
            application_id='app',
            version='1.0.0',
            name='Application',
            short_name='App',
            theme_color='#101010',
            background_color='#FFFFFF',
        )
    )

    assert module.name == 'pwa'
    assert len(module.asset_layers) == 1
    assert module.asset_layers[0].name == 'atlanticus_web_pwa'
    assert '<link rel="manifest" href="/manifest.webmanifest">' in module.index.head_fragments
    assert '<meta name="theme-color" content="#101010">' in module.index.head_fragments
    assert module.index.runtime_config == {
        'service_worker_url': '/service-worker.js',
        'scope': '/',
    }


def test_registration_asset_registers_root_scoped_service_worker() -> None:
    asset = (
        Path(__file__).parents[1]
        / 'src/atlanticus/web/pwa/resources/assets/js/10_pwa_registration.js'
    ).read_text(encoding='utf-8')

    assert 'runtimeConfig.modules?.pwa' in asset
    assert '.register(config.service_worker_url, { scope: config.scope })' in asset
