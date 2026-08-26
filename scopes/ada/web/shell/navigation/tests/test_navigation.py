from pathlib import Path

import dash_bootstrap_components as dbc
import pytest
from dash import html

from ada.web.shell.navigation import (
    ADA_NAVIGATION_ASSET_LAYER,
    AdaNavigationAction,
    AdaNavigationView,
    build_ada_navigation_offcanvas,
    build_ada_navigation_trigger,
    create_ada_navigation_presentation_module,
)
from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.navigation.api import (
    NavigationGroup,
    NavigationLink,
    NavigationMenu,
    NavigationUser,
)


def _menu() -> NavigationMenu:
    return NavigationMenu(
        user=NavigationUser(
            display_name='Local User',
            email='local@example.com',
            profile_key='local',
            profile_label='Local',
            profile_background_color='#3778C2',
            profile_text_color='#FFFFFF',
            avatar_text='LU',
        ),
        links=(
            NavigationLink(
                key='home',
                label='Inicio',
                href='/',
                order=0,
                icon='bi bi-house',
            ),
        ),
        groups=(
            NavigationGroup(
                key='configuration',
                label='Configuración',
                order=10,
                icon='bi bi-gear',
                links=(
                    NavigationLink(
                        key='status',
                        label='Estado',
                        href='/status',
                        icon='bi bi-card-list',
                    ),
                ),
            ),
        ),
    )


def test_module_is_presentation_only() -> None:
    module = create_ada_navigation_presentation_module()

    assert module.name == 'ada-navigation'
    assert module.asset_layers == (ADA_NAVIGATION_ASSET_LAYER,)
    assert ADA_NAVIGATION_ASSET_LAYER.load_order == 210
    assert ADA_NAVIGATION_ASSET_LAYER.package == 'ada.web.shell.navigation'
    assert module.register_services is None
    assert module.register_callbacks is not None


def test_trigger_is_navigation_owned_and_header_agnostic() -> None:
    trigger = build_ada_navigation_trigger()
    props = trigger.to_plotly_json()['props']

    assert isinstance(trigger, html.Button)
    assert props['id'] == 'ada-navigation-trigger'
    assert props['className'] == 'ada-navigation__trigger'
    assert props['title'] == 'Abrir navegación'


def test_offcanvas_uses_injected_view_without_legacy_project_constants() -> None:
    component = build_ada_navigation_offcanvas(
        _menu(),
        view=AdaNavigationView(title='ADA', subtitle='Navegación operacional'),
    )
    payload = str(component.to_plotly_json())

    assert isinstance(component, dbc.Offcanvas)
    assert component.id == 'ada-navigation-offcanvas'
    assert component.placement == 'end'
    assert 'Navegación operacional' in payload
    assert 'ADA N1' not in payload
    assert 'pelambres.cl' not in payload


def test_optional_action_is_rendered_only_when_injected() -> None:
    without_action = str(build_ada_navigation_offcanvas(_menu()).to_plotly_json())
    with_action = str(
        build_ada_navigation_offcanvas(
            _menu(),
            view=AdaNavigationView(
                action=AdaNavigationAction(
                    label='Abrir portal ADA',
                    href='https://example.test/ada',
                    icon='bi bi-grid',
                    new_tab=True,
                )
            ),
        ).to_plotly_json()
    )

    assert 'Abrir portal ADA' not in without_action
    assert 'Abrir portal ADA' in with_action
    assert 'https://example.test/ada' in with_action


def test_user_visuals_come_from_navigation_menu_contract() -> None:
    payload = str(build_ada_navigation_offcanvas(_menu()).to_plotly_json())

    assert 'Local User' in payload
    assert 'local@example.com' in payload
    assert 'Local' in payload
    assert 'LU' in payload
    assert '#3778C2' in payload


def test_view_and_action_reject_empty_required_values() -> None:
    with pytest.raises(WebDefinitionError, match='title must not be empty'):
        AdaNavigationView(title=' ')
    with pytest.raises(WebDefinitionError, match='action href must not be empty'):
        AdaNavigationAction(label='Portal', href=' ')


def test_source_has_no_header_tool_or_project_specific_coupling() -> None:
    root = Path(__file__).parents[1]
    sources = '\n'.join(
        path.read_text(encoding='utf-8') for path in sorted((root / 'src').rglob('*.py'))
    )

    assert 'ToolManifest' not in sources
    assert 'Integrated Operations' not in sources
    assert 'Gestor de configuración' not in sources
    assert 'pelambres.cl' not in sources
    assert 'app-header-' not in sources
    assert 'resolve_navigation_from_services' not in sources


def test_css_is_namespaced_to_navigation_instead_of_dashboard_header() -> None:
    css = (
        Path(__file__).parents[1]
        / 'src'
        / 'ada'
        / 'web'
        / 'shell'
        / 'navigation'
        / 'resources'
        / 'css'
        / '10-navigation.css'
    ).read_text(encoding='utf-8')

    assert '.ada-navigation__trigger' in css
    assert '.ada-navigation__offcanvas' in css
    assert '.ada-navigation__user' in css
    assert '.dashboard-header-shell' not in css
    assert '.dashboard-menu-btn-desktop' not in css
