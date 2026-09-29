from __future__ import annotations

from types import SimpleNamespace

import pytest
from dash import dcc, html

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerCompanionView,
    ManagerDefinitionError,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.web import callbacks as manager_callbacks
from atlanticus.web.manager.web.ids import (
    module_section_panel_id,
    module_status_id,
    primary_view_button_id,
    primary_view_panel_id,
    primary_view_store_id,
)
from atlanticus.web.manager.web.layout import build_module_content
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey


class _Coordinator:
    def get_status(self, module_key, principal):
        return None

    def can_load_history(self, module_key, principal):
        return False


class _Recorder:
    def __init__(self):
        self.callbacks = {}

    def callback(self, *_args, **_kwargs):
        def register(function):
            self.callbacks[function.__name__] = function
            return function
        return register


def _module(*, companion=True, default='companion'):
    return ManagerModule(
        key='assets',
        group_key='configuration',
        title='Administración de activos',
        route='/assets',
        order=10,
        layout=lambda _services: html.Div('Catálogo configurable'),
        source_key=SourceKey('assets'),
        source_service='assets.source',
        source_reader_service='assets.reader',
        projection_service='assets.projection',
        draft_validation_service='assets.validation',
        companion_view=(
            ManagerCompanionView('Asignaciones', lambda _services: html.Div('Asignación individual'))
            if companion else None
        ),
        primary_view_title='Catálogo de activos' if companion else None,
        default_primary_view=default,
    )


def _find(component, component_id):
    if getattr(component, 'id', None) == component_id:
        return component
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for item in children:
            found = _find(item, component_id)
            if found is not None:
                return found
    elif children is not None and not isinstance(children, str):
        return _find(children, component_id)
    return None


def _text(component):
    if isinstance(component, str):
        return component
    if isinstance(component, (list, tuple)):
        return ' '.join(_text(item) for item in component)
    return _text(getattr(component, 'children', None)) if component is not None else ''


def test_companion_view_preserves_distinct_module_workflow():
    module = _module()
    layout = build_module_content(
        module=module,
        services=ServiceRegistry(),
        coordinator=_Coordinator(),
        principal=ManagerPrincipal('local', 'Local', is_local=True),
    )
    selected = _find(layout, primary_view_store_id(module.key))
    assert isinstance(selected, dcc.Store)
    assert selected.data == 'companion'
    companion = _find(layout, primary_view_panel_id(module.key, 'companion'))
    module_panel = _find(layout, primary_view_panel_id(module.key, 'module'))
    assert companion.className.endswith('--active')
    assert not module_panel.className.endswith('--active')
    assert 'Asignación individual' in _text(companion)
    assert 'Catálogo configurable' in _text(module_panel)
    assert 'Estado y trazabilidad' in _text(module_panel)
    assert _find(companion, module_status_id(module.key)) is None
    assert _find(module_panel, module_status_id(module.key)) is not None
    assert _find(module_panel, module_section_panel_id(module.key, 'content')) is not None
    assert _find(companion, module_section_panel_id(module.key, 'workflow')) is None
    assert _find(layout, primary_view_button_id(module.key, 'companion')).children == 'Asignaciones'
    assert _find(layout, primary_view_button_id(module.key, 'module')).children == 'Catálogo de activos'


def test_normal_module_keeps_original_manager_layout():
    module = _module(companion=False, default='module')
    layout = build_module_content(
        module=module,
        services=ServiceRegistry(),
        coordinator=_Coordinator(),
        principal=ManagerPrincipal('local', 'Local', is_local=True),
    )
    assert _find(layout, primary_view_store_id(module.key)) is None
    assert _find(layout, module_status_id(module.key)) is not None
    assert _find(layout, module_section_panel_id(module.key, 'workflow')) is not None


def test_companion_must_be_configured_for_default_navigation():
    with pytest.raises(ManagerDefinitionError, match='requires a companion'):
        _module(companion=False, default='companion')
    with pytest.raises(ManagerDefinitionError, match='title'):
        ManagerCompanionView('  ', lambda _services: None)
    with pytest.raises(ManagerDefinitionError, match='invalid'):
        _module(default='other')
    with pytest.raises(ManagerDefinitionError, match='invalid type'):
        module = _module()
        module.__class__(
            **{field: getattr(module, field) for field in module.__dataclass_fields__ if field != 'companion_view'},
            companion_view='invalid',
        )


def test_view_switching_changes_only_panel_visibility(monkeypatch):
    principal = ManagerPrincipal('local', 'Local', is_local=True)
    module = _module()
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: principal,
        groups=(ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        modules=(module,),
    )
    app = _Recorder()
    manager_callbacks.register_manager_callbacks(
        app,
        definition=definition,
        registry=ManagerModuleRegistry(definition.groups, definition.modules),
        services=ServiceRegistry(),
        authorization=DefaultManagerAuthorizationPolicy(),
    )
    selected = SimpleNamespace(triggered_id=primary_view_button_id(module.key, 'module'))
    monkeypatch.setattr(manager_callbacks, 'ctx', selected)
    buttons = [
        primary_view_button_id(module.key, 'companion'),
        primary_view_button_id(module.key, 'module'),
    ]
    assert app.callbacks['select_primary_view']([0, 1], buttons, 'companion') == 'module'
    assert app.callbacks['select_primary_view']([0, 0], buttons, 'companion') == 'companion'
    active = app.callbacks['render_primary_view']('module')
    assert not active[0].endswith('--active')
    assert active[1].endswith('--active')
    assert active[3].endswith('--active')
    assert app.callbacks['render_primary_view']('companion')[0].endswith('--active')
