from __future__ import annotations

import pytest
from dash import dcc, html

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerEntry,
    ManagerHeaderBrandMark,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.errors import ManagerDefinitionError
from atlanticus.web.manager.web.header import build_manager_header


def _context():
    group = ManagerModuleGroup('admin', 'Administración', 10)
    entry = ManagerEntry('users', 'admin', 'Usuarios', '/users', 10, lambda _: None)
    principal = ManagerPrincipal('local:jane-doe', 'Jane Doe')
    registry = ManagerModuleRegistry((group,), (), entries=(entry,), route_prefix='/manager')
    return group, entry, principal, registry


def _descendants(root, kind):
    if isinstance(root, kind):
        yield root
    children = getattr(root, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _descendants(child, kind)
    elif children is not None and not isinstance(children, str):
        yield from _descendants(children, kind)


def test_generic_manager_header_needs_no_project_brand():
    _, _, principal, registry = _context()
    header = build_manager_header(
        registry=registry, principal=principal, application_home_href=None,
    )
    assert not tuple(_descendants(header, html.Img))
    assert any(node.children == 'Manager' for node in _descendants(header, html.Strong))
    assert [node.href for node in _descendants(header, dcc.Link)] == ['/manager']


def test_host_marks_are_rendered_with_accessible_order_and_without_dropping_controls():
    _, _, principal, registry = _context()
    marks = (
        ManagerHeaderBrandMark('organization', '/assets/example/img/mlp.png', 'MLP'),
        ManagerHeaderBrandMark('product', '/assets/example/img/ada.svg', 'ADA'),
        ManagerHeaderBrandMark('framework', '/assets/example/img/framework.png', 'Atlanticus'),
    )
    header = build_manager_header(
        registry=registry, principal=principal, application_home_href='/',
        brand_marks=marks, title='Gestor de configuración ADA',
        subtitle='Configuraciones revisionadas',
    )
    images = tuple(_descendants(header, html.Img))
    assert [node.alt for node in images] == ['ADA', 'Atlanticus', 'MLP']
    assert [node.src for node in images] == [
        '/assets/example/img/ada.svg',
        '/assets/example/img/framework.png',
        '/assets/example/img/mlp.png',
    ]
    assert [node.href for node in _descendants(header, dcc.Link)] == ['/manager', '/']
    assert all(node.children != principal.display_name for node in _descendants(header, html.Span))
    assert any(node.children == 'Gestor de configuración ADA' for node in _descendants(header, html.Strong))


def test_surface_rejects_duplicate_marks_and_unsupported_values():
    group, entry, principal, _registry = _context()
    mark = ManagerHeaderBrandMark('product', '/assets/example/img/ada.svg', 'ADA')
    with pytest.raises(ManagerDefinitionError, match='duplicated'):
        ManagerSurfaceDefinition(
            principal_provider=lambda: principal,
            groups=(group,), modules=(), entries=(entry,), header_brand_marks=(mark, mark),
        )
    with pytest.raises(ManagerDefinitionError, match='role'):
        ManagerHeaderBrandMark('ada', '/assets/example/img/ada.svg', 'ADA')
    with pytest.raises(ManagerDefinitionError, match='local asset'):
        ManagerHeaderBrandMark('product', 'https://example.org/logo.svg', 'Logo')


def test_surface_keeps_external_brand_configuration_outside_generic_default():
    group, entry, principal, _registry = _context()
    marks = (ManagerHeaderBrandMark('product', '/assets/example/img/ada.svg', 'ADA'),)
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: principal,
        groups=(group,), modules=(), entries=(entry,), header_brand_marks=marks,
        header_title='Manager personalizado',
    )
    assert definition.header_brand_marks == marks
    assert definition.header_title == 'Manager personalizado'
