from __future__ import annotations

import pytest
from dash import dcc, html

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerEntry,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.errors import ManagerDefinitionError
from atlanticus.web.manager.web.header import (
    build_manager_header,
    resolve_manager_header_section,
)
from atlanticus.web.manager.web.ids import HEADER_SECTION_ID


def _context():
    group = ManagerModuleGroup('administration', 'Administración', 10)
    entries = (
        ManagerEntry('public', 'administration', 'Herramientas', '/tools', 10,
                     lambda _services: None, access_key='tools.manage'),
        ManagerEntry('secret', 'administration', 'Restringido', '/secret', 20,
                     lambda _services: None, access_key='secret.manage'),
    )
    registry = ManagerModuleRegistry((group,), (), entries=entries, route_prefix='/manager')
    principal = ManagerPrincipal('jane', 'Jane Doe', access_keys=('tools.manage',))
    return registry, principal, DefaultManagerAuthorizationPolicy()


def _find(component: object, component_id: object) -> object | None:
    if getattr(component, 'id', None) == component_id:
        return component
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if child is not None:
                result = _find(child, component_id)
                if result is not None:
                    return result
    elif children is not None and not isinstance(children, str):
        return _find(children, component_id)
    return None


def _texts(component: object) -> tuple[str, ...]:
    if isinstance(component, str):
        return (component,)
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        return tuple(text for child in children for text in _texts(child))
    if children is None:
        return ()
    return _texts(children)


def _links(component: object) -> tuple[dcc.Link, ...]:
    result = [component] if isinstance(component, dcc.Link) else []
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if child is not None:
                result.extend(_links(child))
    elif children is not None and not isinstance(children, str):
        result.extend(_links(children))
    return tuple(result)


def test_header_is_generic_and_return_is_opt_in():
    registry, principal, _policy = _context()
    standalone = build_manager_header(
        registry=registry, principal=principal, application_home_href=None,
    )
    integrated = build_manager_header(
        registry=registry, principal=principal, application_home_href='/',
    )
    assert isinstance(standalone, html.Header)
    assert _find(standalone, HEADER_SECTION_ID).children == 'Inicio'
    assert [link.href for link in _links(standalone)] == ['/manager']
    assert [link.href for link in _links(integrated)] == ['/manager', '/']
    assert principal.display_name not in _texts(integrated)


@pytest.mark.parametrize('value', ['https://example.org', '//example.org', '/manager?next=/x',
                                    '/manager/', 'relative', ''])
def test_external_or_ambiguous_return_routes_are_rejected(value):
    registry, principal, _ = _context()
    with pytest.raises(ManagerDefinitionError, match='internal path'):
        ManagerSurfaceDefinition(
            principal_provider=lambda: principal,
            groups=registry.groups,
            modules=(),
            entries=registry.entries,
            application_home_href=value,
        )


def test_internal_return_paths_are_supported():
    registry, principal, _ = _context()
    for href in (None, '/', '/dashboard'):
        definition = ManagerSurfaceDefinition(
            principal_provider=lambda: principal,
            groups=registry.groups,
            modules=(),
            entries=registry.entries,
            application_home_href=href,
        )
        assert definition.application_home_href == href


def test_header_context_tracks_authorized_route_without_leaking_titles():
    registry, principal, policy = _context()
    values = {
        None: 'Inicio',
        '/manager': 'Inicio',
        '/manager/tools': 'Herramientas',
        '/manager/secret': 'Administración',
        '/manager/missing': 'Administración',
    }
    for pathname, expected in values.items():
        assert resolve_manager_header_section(
            pathname=pathname,
            registry=registry,
            principal=principal,
            authorization=policy,
        ) == expected
