from inspect import signature

import pytest
from dash import Input, State

pytest.importorskip('dash')

from atlanticus.web.navigation.configuration.adapters.memory import (
    MemoryNavigationConfigurationStore,
    MemoryNavigationProjectionRepository,
)
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.services import (
    compose_navigation_configuration_services,
)
from atlanticus.web.navigation.configuration.web import (
    NavigationAdminWebContext,
    build_navigation_admin_configuration,
    create_navigation_admin_web_module,
)
from atlanticus.web.navigation.configuration.web.callbacks import (
    register_navigation_admin_callbacks,
)
from atlanticus.web.navigation.configuration.web.ids import (
    CATALOG_STORE_ID,
    LINK_PROFILES_ID,
    LINK_SECTION_ID,
    PROJECTION_NAME_ID,
    SOURCE_NAME_ID,
    SOURCE_REVISION_STORE_ID,
    STRUCTURE_ID,
)


class _CallbackRecorder:
    def __init__(self) -> None:
        self.callbacks: dict[str, tuple[tuple[object, ...], dict[str, object], object]] = {}

    def callback(self, *dependencies: object, **options: object):
        def register(function):
            self.callbacks[function.__name__] = (dependencies, options, function)
            return function

        return register


def _context() -> NavigationAdminWebContext:
    source = MemoryNavigationConfigurationStore()
    services = compose_navigation_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryNavigationProjectionRepository(),
        audit_actor_provider=lambda: 'tester',
    )
    return NavigationAdminWebContext(
        services=services,
        draft_store_id='draft',
        saved_draft_store_id='saved-draft',
        draft_save_action_id='save',
        workflow_refresh_signal_id='refresh',
        editor_revision_store_id='editor-revision',
        draft_owner_provider=lambda: 'tester',
        source_name='Navigation Source',
        projection_name='Navigation Projection',
    )


def _walk(component: object):
    yield component
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if child is not None:
                yield from _walk(child)
    elif children is not None and not isinstance(children, (str, int, float, bool)):
        yield from _walk(children)


def _component(layout: object, component_id: object) -> object:
    for item in _walk(layout):
        if getattr(item, 'id', None) == component_id:
            return item
    raise AssertionError(f'Component {component_id!r} was not found')


def _text(component: object) -> str:
    children = getattr(component, 'children', None)
    if isinstance(children, str):
        return children
    return ''


def test_navigation_admin_layout_starts_with_empty_local_workspace(monkeypatch) -> None:
    context = _context()

    def fail_if_source_is_loaded():
        raise AssertionError(
            'Navigation source must not be loaded while building the editor layout'
        )

    monkeypatch.setattr(context.services.administration, 'load_source', fail_if_source_is_loaded)

    layout = build_navigation_admin_configuration(context)
    catalog = NavigationConfigurationCatalog.from_document(
        _component(layout, CATALOG_STORE_ID).data
    )

    assert catalog.links == ()
    assert catalog.groups == ()
    assert _component(layout, SOURCE_REVISION_STORE_ID).data is None
    assert _text(_component(layout, SOURCE_NAME_ID)) == 'Navigation Source'
    assert _text(_component(layout, PROJECTION_NAME_ID)) == 'Navigation Projection'
    assert _component(layout, STRUCTURE_ID) is not None


def test_navigation_admin_exposes_functional_section_and_profile_selectors() -> None:
    layout = build_navigation_admin_configuration(_context())

    section = _component(layout, LINK_SECTION_ID)
    profiles = _component(layout, LINK_PROFILES_ID)

    assert section.searchable is True
    assert section.clearable is False
    assert section.placeholder == 'Sin sección / raíz'
    assert profiles.searchable is True
    assert profiles.multi is True
    assert profiles.placeholder == 'Seleccionar perfiles'


def test_navigation_admin_web_module_owns_its_asset_layer() -> None:
    module = create_navigation_admin_web_module(_context())

    assert module.name == 'atlanticus-navigation-configuration'
    assert len(module.asset_layers) == 1
    assert module.asset_layers[0].name == 'atlanticus_navigation_configuration'
    assert module.asset_layers[0].package == 'atlanticus.web.navigation.configuration'


def test_navigation_admin_callback_registration_matches_function_arity() -> None:
    recorder = _CallbackRecorder()
    register_navigation_admin_callbacks(recorder, _context())

    assert recorder.callbacks

    for name, (dependencies, _options, function) in recorder.callbacks.items():
        inputs_and_states = sum(
            isinstance(dependency, (Input, State)) for dependency in dependencies
        )
        positional_parameters = len(
            [
                parameter
                for parameter in signature(function).parameters.values()
                if parameter.kind
                in {
                    parameter.POSITIONAL_ONLY,
                    parameter.POSITIONAL_OR_KEYWORD,
                }
            ]
        )
        assert positional_parameters == inputs_and_states, name
