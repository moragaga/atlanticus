from pathlib import Path

from dash import html, page_container

from atlanticus.web.application import create_web_application
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.observability import WEB_OBSERVABILITY_SERVICE_KEY, WebObservability


def _build_page_package(tmp_path: Path) -> str:
    package = tmp_path / 'test_observability_service_pages'
    package.mkdir()
    (package / '__init__.py').write_text('', encoding='utf-8')
    (package / 'home.py').write_text(
        'from dash import html, register_page\n'
        "register_page(__name__, path='/', name='Home')\n"
        "layout = html.Div('Home')\n",
        encoding='utf-8',
    )
    return package.name


def test_framework_observability_is_available_as_frozen_application_service(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page_package = _build_page_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    runtime = create_web_application(
        WebApplicationDefinition(
            import_name='test_observability_service_web',
            metadata=ApplicationMetadata(
                application_id='test-observability-service-web',
                display_name='Test',
                version='0.1.0',
            ),
            publications_root=tmp_path / 'published',
            layout=lambda _services: html.Div([html.Div('Test'), page_container]),
            page_packages=(page_package,),
        )
    )

    registered = runtime.services.require(WEB_OBSERVABILITY_SERVICE_KEY, WebObservability)

    assert registered is runtime.observability
    assert runtime.services.frozen is True
