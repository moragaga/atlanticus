from pathlib import Path

import pytest
from dash import html, page_container

from atlanticus.web.application import create_web_application
from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry


def _build_page_package(
    tmp_path: Path,
    *,
    package_name: str,
    module_name: str = 'home',
    route: str = '/',
) -> str:
    package = tmp_path / package_name
    package.mkdir()
    (package / '__init__.py').write_text('', encoding='utf-8')
    (package / f'{module_name}.py').write_text(
        'from dash import html, register_page\n'
        f'register_page(__name__, path={route!r}, name={module_name.title()!r})\n'
        f'layout = html.Div({module_name.title()!r})\n',
        encoding='utf-8',
    )
    return package_name


def _definition(
    tmp_path: Path,
    *,
    import_name: str,
    page_packages: tuple[str, ...],
    modules: tuple[WebModule, ...] = (),
) -> WebApplicationDefinition:
    return WebApplicationDefinition(
        import_name=import_name,
        metadata=ApplicationMetadata(
            application_id=import_name.replace('_', '-'),
            display_name=import_name.replace('_', ' ').title(),
            version='0.1.0',
        ),
        publications_root=tmp_path / f'{import_name}-publications',
        layout=lambda _services: html.Main(page_container),
        modules=modules,
        page_packages=page_packages,
    )


def test_minimal_application_runs_without_optional_capabilities(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page_package = _build_page_package(
        tmp_path,
        package_name='minimal_pages',
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    runtime = create_web_application(
        _definition(
            tmp_path,
            import_name='minimal_web',
            page_packages=(page_package,),
        )
    )

    assert runtime.dash.server is runtime.server
    assert len(runtime.services) == 0
    assert runtime.page_modules == ('minimal_pages.home',)


def test_declared_service_requirement_is_independent_from_module_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page_package = _build_page_package(
        tmp_path,
        package_name='service_order_pages',
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    observed: list[str] = []

    def register_consumer_callbacks(_app: object, services: ServiceRegistry) -> None:
        observed.append(services.require('example.service', str))

    consumer = WebModule(
        name='consumer',
        register_callbacks=register_consumer_callbacks,
        requires_services=('example.service',),
    )

    def register_provider(services: ServiceRegistry) -> None:
        services.add('example.service', 'ready')

    provider = WebModule(
        name='provider',
        register_services=register_provider,
    )

    runtime = create_web_application(
        _definition(
            tmp_path,
            import_name='service_order_web',
            page_packages=(page_package,),
            modules=(consumer, provider),
        )
    )

    assert runtime.services.require('example.service', str) == 'ready'
    assert observed == ['ready']


def test_missing_declared_service_requirement_fails_startup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page_package = _build_page_package(
        tmp_path,
        package_name='missing_service_pages',
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    with pytest.raises(
        WebDefinitionError,
        match='Module requires an unregistered service: consumer: missing.service',
    ):
        create_web_application(
            _definition(
                tmp_path,
                import_name='missing_service_web',
                page_packages=(page_package,),
                modules=(
                    WebModule(
                        name='consumer',
                        requires_services=('missing.service',),
                    ),
                ),
            )
        )


def test_duplicate_required_service_declaration_fails_definition(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page_package = _build_page_package(
        tmp_path,
        package_name='duplicate_required_service_pages',
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    with pytest.raises(
        WebDefinitionError,
        match='Module required service is duplicated: consumer: shared.service',
    ):
        create_web_application(
            _definition(
                tmp_path,
                import_name='duplicate_required_service_web',
                page_packages=(page_package,),
                modules=(
                    WebModule(
                        name='consumer',
                        requires_services=('shared.service', 'shared.service'),
                    ),
                ),
            )
        )


def test_duplicate_page_route_from_independent_capabilities_fails_startup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first_package = _build_page_package(
        tmp_path,
        package_name='first_capability_pages',
        route='/shared',
    )
    second_package = _build_page_package(
        tmp_path,
        package_name='second_capability_pages',
        route='/shared',
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    with pytest.raises(WebDefinitionError, match='Page route is duplicated: /shared'):
        create_web_application(
            _definition(
                tmp_path,
                import_name='duplicate_route_web',
                page_packages=(),
                modules=(
                    WebModule(name='first-capability', page_packages=(first_package,)),
                    WebModule(name='second-capability', page_packages=(second_package,)),
                ),
            )
        )


def test_invalid_required_service_name_fails_definition(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page_package = _build_page_package(
        tmp_path,
        package_name='invalid_required_service_pages',
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    with pytest.raises(
        WebDefinitionError,
        match='Module required service name has an invalid format: consumer',
    ):
        create_web_application(
            _definition(
                tmp_path,
                import_name='invalid_required_service_web',
                page_packages=(page_package,),
                modules=(
                    WebModule(
                        name='consumer',
                        requires_services=(' invalid.service ',),
                    ),
                ),
            )
        )
