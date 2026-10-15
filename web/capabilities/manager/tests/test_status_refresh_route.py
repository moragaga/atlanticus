from types import SimpleNamespace

import pytest
from dash.exceptions import PreventUpdate

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.web import callbacks as callbacks_module
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey


class RecorderApp:
    def __init__(self) -> None:
        self.callbacks = []

    def callback(self, *dependencies, **options):
        def register(function):
            self.callbacks.append(function)
            return function
        return register


@pytest.fixture
def registered(monkeypatch):
    def build(route_prefix: str):
        calls = []

        class Coordinator:
            def __init__(self, **kwargs):
                pass

            def get_status(self, module_key, principal):
                calls.append((module_key, principal.subject_id))
                return SimpleNamespace(source_current_release=None)

        monkeypatch.setattr(callbacks_module, 'ManagerProjectionCoordinator', Coordinator)
        principal = ManagerPrincipal(
            'local', 'Local', access_keys=('tools.manage',), is_local=True
        )
        module = ManagerModule(
            key='tools',
            group_key='configuration',
            title='Tools',
            route='/tools',
            order=10,
            layout=lambda _services: None,
            source_key=SourceKey('tools'),
            source_service='tools.source',
            source_reader_service='tools.reader',
            projection_service='tools.projection',
            draft_validation_service='tools.validation',
            access_key='tools.manage',
        )
        definition = ManagerSurfaceDefinition(
            principal_provider=lambda: principal,
            groups=(ManagerModuleGroup('configuration', 'Configuration', 10),),
            modules=(module,),
            route_prefix=route_prefix,
        )
        registry = ManagerModuleRegistry(
            definition.groups, definition.modules, route_prefix=route_prefix
        )
        app = RecorderApp()
        callbacks_module.register_manager_callbacks(
            app,
            definition=definition,
            registry=registry,
            services=ServiceRegistry(),
            authorization=DefaultManagerAuthorizationPolicy(),
        )
        callback = next(
            function for function in app.callbacks if function.__name__ == 'refresh_statuses'
        )
        return callback, calls

    return build


@pytest.mark.parametrize('pathname', [None, '/', '/dashboard', '/managerial', '/other/manager'])
def test_operational_routes_do_not_query_manager(registered, pathname):
    callback, calls = registered('/manager')

    with pytest.raises(PreventUpdate):
        callback(0, pathname, [])

    assert calls == []


@pytest.mark.parametrize('pathname', ['/manager', '/manager/tools', '/manager/tools/subpage'])
def test_manager_routes_load_visible_statuses(registered, pathname):
    callback, calls = registered('/manager')

    statuses, summary = callback(0, pathname, [])

    assert statuses == {'tools': 'no_source'}
    assert summary is not None
    assert calls == [('tools', 'local')]


def test_refresh_signals_still_load_statuses_inside_manager(registered):
    callback, calls = registered('/manager')

    callback(0, '/manager', [])
    callback(1, '/manager', [1])
    with pytest.raises(PreventUpdate):
        callback(2, '/', [2])
    callback(3, '/manager/tools', [3])

    assert calls == [('tools', 'local')] * 3


@pytest.mark.parametrize('pathname', [None, '/', '/tools'])
def test_unprefixed_standalone_manager_keeps_existing_behavior(registered, pathname):
    callback, calls = registered('')

    statuses, _summary = callback(0, pathname, [])

    assert statuses == {'tools': 'no_source'}
    assert calls == [('tools', 'local')]
