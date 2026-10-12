import pytest

from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.pwa import WebFavicon, WebPwaDefinition, WebPwaIcon, create_web_pwa_module


def _definition(*, browser_favicon=None):
    return WebPwaDefinition(
        application_id='app',
        version='1.0.0',
        name='Application',
        short_name='App',
        theme_color='#101010',
        background_color='#FFFFFF',
        icons=(WebPwaIcon('/assets/pwa-192.png', '192x192'),),
        browser_favicon=browser_favicon,
    )


def test_explicit_browser_favicon_replaces_implicit_pwa_link_only():
    definition = _definition(browser_favicon=WebFavicon('/assets/tool/img/favicon.png?v=123'))
    module = create_web_pwa_module(definition)

    links = [fragment for fragment in module.index.head_fragments if 'rel="icon"' in fragment]
    assert links == [
        '<link rel="icon" type="image/png" href="/assets/tool/img/favicon.png?v=123">'
    ]
    assert definition.to_manifest()['icons'] == [
        {
            'src': '/assets/pwa-192.png',
            'sizes': '192x192',
            'type': 'image/png',
            'purpose': 'any',
        }
    ]
    assert 'browser_favicon' not in definition.to_manifest()


def test_missing_browser_favicon_preserves_first_pwa_icon():
    module = create_web_pwa_module(_definition())
    links = [fragment for fragment in module.index.head_fragments if 'rel="icon"' in fragment]
    assert links == ['<link rel="icon" type="image/png" href="/assets/pwa-192.png">']


def test_explicit_browser_favicon_without_pwa_icons():
    definition = _definition(browser_favicon=WebFavicon('/assets/favicon.png'))
    definition = WebPwaDefinition(
        application_id=definition.application_id,
        version=definition.version,
        name=definition.name,
        short_name=definition.short_name,
        theme_color=definition.theme_color,
        background_color=definition.background_color,
        browser_favicon=definition.browser_favicon,
    )
    module = create_web_pwa_module(definition)
    links = [fragment for fragment in module.index.head_fragments if 'rel="icon"' in fragment]
    assert links == ['<link rel="icon" type="image/png" href="/assets/favicon.png">']
    assert 'icons' not in definition.to_manifest()


@pytest.mark.parametrize('src', ['favicon.png', '//example.com/favicon.png', '/favicon.png\n'])
def test_browser_favicon_rejects_invalid_paths(src):
    with pytest.raises(WebDefinitionError, match='Browser favicon src'):
        WebFavicon(src)


def test_browser_favicon_rejects_invalid_contract_type():
    with pytest.raises(WebDefinitionError, match='Browser favicon must be'):
        _definition(browser_favicon='/assets/favicon.png')
