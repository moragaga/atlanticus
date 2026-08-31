import pytest

from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.models import ApplicationMetadata
from atlanticus.web.pwa import WebPwaDefinition, WebPwaIcon


def test_definition_derives_application_metadata_without_tool_names() -> None:
    metadata = ApplicationMetadata(
        application_id='ada-generic-application',
        display_name='ADA',
        version='0.3.0',
    )
    definition = WebPwaDefinition.from_application(
        metadata,
        short_name='ADA',
        theme_color='#5B5C64',
        background_color='#E1E1E1',
        icons=(WebPwaIcon('/assets/ada-192.png', '192x192'),),
    )

    assert definition.to_manifest() == {
        'id': 'ada-generic-application',
        'name': 'ADA',
        'short_name': 'ADA',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'theme_color': '#5B5C64',
        'background_color': '#E1E1E1',
        'icons': [
            {
                'src': '/assets/ada-192.png',
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any',
            }
        ],
    }


def test_definition_rejects_non_absolute_application_paths() -> None:
    with pytest.raises(WebDefinitionError, match='start URL'):
        WebPwaDefinition(
            application_id='app',
            version='1.0.0',
            name='App',
            short_name='App',
            theme_color='#000000',
            background_color='#FFFFFF',
            start_url='app',
        )
