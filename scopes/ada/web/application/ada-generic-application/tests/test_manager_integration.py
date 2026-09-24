from dash import dcc, html

from ada.web.application.generic.manager_integration import (
    MANAGER_SURFACE_ID,
    OPERATIONAL_SURFACE_ID,
    integrate_manager_surface,
)
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

_MANAGER_LOCATION_ID = 'integration-test-manager-location'


class ManagerSurfaceStub:
    @property
    def web_modules(self):
        return (WebModule(name='test-manager-module'),)

    def layout(self, _services: ServiceRegistry):
        return html.Div([dcc.Location(id=_MANAGER_LOCATION_ID), html.Div(id='test-manager-content')])


def _base_definition(tmp_path):
    return WebApplicationDefinition(
        import_name='ada.web.application.generic',
        metadata=ApplicationMetadata('ada-generic-application', 'ADA', '0.2.17'),
        publications_root=tmp_path / 'publications',
        layout=lambda _services: html.Div(id='test-operational-content'),
        modules=(WebModule(name='test-operational-module'),),
        page_packages=('ada.web.application.generic.pages',),
    )


def _integrated(tmp_path):
    return integrate_manager_surface(
        _base_definition(tmp_path),
        manager=ManagerSurfaceStub(),
        page_packages=('ada.web.application.configuration_manager.pages',),
        route_prefix='/manager',
        location_id=_MANAGER_LOCATION_ID,
    )


def test_integration_reuses_one_definition_and_registers_both_surfaces(tmp_path):
    definition = _integrated(tmp_path)

    assert tuple(module.name for module in definition.modules) == (
        'test-operational-module',
        'test-manager-module',
        'ada-manager-surface-router',
    )
    assert definition.page_packages == (
        'ada.web.application.generic.pages',
        'ada.web.application.configuration_manager.pages',
    )
    layout = definition.layout(ServiceRegistry())
    assert layout.id == 'ada-integrated-application'
    assert [child.id for child in layout.children] == (
        [OPERATIONAL_SURFACE_ID, MANAGER_SURFACE_ID]
    )
    assert all(child.hidden is True for child in layout.children)


def test_manager_route_selection_preserves_operational_route_boundary(tmp_path):
    definition = _integrated(tmp_path)
    router = definition.modules[-1]
    callbacks = {}

    class AppStub:
        def callback(self, *_args, **_kwargs):
            def capture(callback):
                callbacks['select'] = callback
                return callback

            return capture

    router.register_callbacks(AppStub(), ServiceRegistry())
    select = callbacks['select']

    assert select('/') == (False, True)
    assert select('/manager') == (True, False)
    assert select('/manager/users') == (True, False)
    assert select('/manager-other') == (False, True)


def test_duplicate_modules_fail_before_mounting(tmp_path):
    import pytest

    definition = _base_definition(tmp_path)
    duplicate_manager = ManagerSurfaceStub()
    definition = WebApplicationDefinition(
        import_name=definition.import_name,
        metadata=definition.metadata,
        publications_root=definition.publications_root,
        layout=definition.layout,
        modules=(WebModule(name='test-manager-module'),),
        page_packages=definition.page_packages,
    )

    with pytest.raises(ValueError, match='unique names'):
        integrate_manager_surface(
            definition,
            manager=duplicate_manager,
            page_packages=('ada.web.application.configuration_manager.pages',),
            route_prefix='/manager',
            location_id=_MANAGER_LOCATION_ID,
        )
