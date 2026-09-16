
import pytest
pytest.importorskip('dash')

from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.web import (
    NavigationAdminWebContext,
    build_navigation_admin_configuration,
    create_navigation_admin_web_module,
)
from atlanticus.web.navigation.configuration.web.ids import (
    CATALOG_STORE_ID,
    LINK_PROFILES_ID,
    LINK_SECTION_ID,
    PROJECTION_NAME_ID,
    SOURCE_NAME_ID,
    STRUCTURE_ID,
)


def _context() -> NavigationAdminWebContext:
    return NavigationAdminWebContext(
        workspace_payload_reader=lambda document: (
            dict(document['payload'])
            if isinstance(document, dict) and isinstance(document.get('payload'), dict)
            else None
        ),
        workspace_payload_writer=lambda document, payload: {
            **(document or {}),
            'payload': dict(payload),
        },
        draft_store_id='draft',
        saved_draft_store_id='saved-draft',
        draft_save_action_id={'type': 'save', 'module': 'navigation'},
        editor_revision_store_id='editor-revision',
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


def test_navigation_admin_layout_starts_with_empty_editor_payload() -> None:
    layout = build_navigation_admin_configuration(_context())
    catalog = NavigationConfigurationCatalog.from_document(
        _component(layout, CATALOG_STORE_ID).data
    )

    assert catalog.links == ()
    assert catalog.groups == ()
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


