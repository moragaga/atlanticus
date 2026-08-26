from pathlib import Path

import dash_bootstrap_components as dbc
import pytest

from ada.web.shell.navigation import (
    ADA_NAVIGATION_ASSET_LAYER,
    AdaNavigationAction,
    AdaNavigationView,
    build_ada_navigation_desktop_trigger,
    build_ada_navigation_mobile_trigger,
    build_ada_navigation_offcanvas,
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


def test_approved_desktop_trigger_pattern_is_preserved_without_header_owned_ids() -> None:
    trigger = build_ada_navigation_desktop_trigger()
    props = trigger.to_plotly_json()['props']
    payload = str(trigger.to_plotly_json())

    assert isinstance(trigger, dbc.Button)
    assert props['id'] == 'ada-navigation-desktop-toggle'
    assert props['className'] == (
        'ada-navigation__trigger ada-navigation__trigger--desktop d-none d-md-flex dark-theme'
    )
    assert props['color'] == 'dark'
    assert props['n_clicks'] == 0
    assert 'bi-chevron-left' in payload


def test_approved_mobile_trigger_pattern_is_preserved() -> None:
    trigger = build_ada_navigation_mobile_trigger()
    props = trigger.to_plotly_json()['props']
    payload = str(trigger.to_plotly_json())

    assert isinstance(trigger, dbc.Button)
    assert props['id'] == 'ada-navigation-mobile-toggle'
    assert 'ada-navigation__trigger--mobile' in props['className']
    assert 'bi-list' in payload


def test_offcanvas_preserves_navigation_pattern_with_injected_view() -> None:
    component = build_ada_navigation_offcanvas(
        _menu(),
        view=AdaNavigationView(
            title='Asistente de Decisiones Ágiles',
            brand_logo_src='/assets/ada/logo.svg',
            footer_logo_src='/assets/ada/pelambres.svg',
            application_version='0.1.5',
        ),
    )
    payload = str(component.to_plotly_json())

    assert isinstance(component, dbc.Offcanvas)
    assert component.id == 'ada-navigation-offcanvas'
    assert component.className == 'ada-navigation__offcanvas'
    assert component.placement == 'end'
    assert component.is_open is False
    assert 'ada-navigation__brand-logo' in payload
    assert '/assets/ada/logo.svg' in payload
    assert 'Asistente de Decisiones Ágiles' in payload
    assert 'ada-navigation__footer-logo' in payload
    assert '/assets/ada/pelambres.svg' in payload
    assert 'Versión 0.1.5' in payload
    assert 'ADA N1' not in payload
    assert 'pelambres.cl' not in payload


def test_user_card_preserves_centered_avatar_profile_pattern() -> None:
    payload = str(build_ada_navigation_offcanvas(_menu()).to_plotly_json())

    assert 'ada-navigation__user' in payload
    assert 'ada-navigation__avatar ada-navigation__avatar--fallback' in payload
    assert 'ada-navigation__user-copy' in payload
    assert 'ada-navigation__profile' in payload
    assert 'Local User' in payload
    assert 'local@example.com' in payload
    assert 'LU' in payload
    assert '#3778C2' in payload


def test_optional_action_preserves_master_action_pattern_when_injected() -> None:
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

    assert 'ada-navigation__action' not in without_action
    assert 'ada-navigation__action' in with_action
    assert 'Abrir portal ADA' in with_action
    assert 'https://example.test/ada' in with_action


def test_view_and_action_reject_empty_required_values() -> None:
    with pytest.raises(WebDefinitionError, match='title must not be empty'):
        AdaNavigationView(title=' ')
    with pytest.raises(WebDefinitionError, match='brand logo source must not be empty'):
        AdaNavigationView(brand_logo_src=' ')
    with pytest.raises(WebDefinitionError, match='application version must not be empty'):
        AdaNavigationView(application_version=' ')
    with pytest.raises(WebDefinitionError, match='action href must not be empty'):
        AdaNavigationAction(label='Portal', href=' ')


def test_source_remains_decoupled_from_header_tool_and_project_specific_data() -> None:
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


def test_css_preserves_approved_visual_navigation_pattern_with_navigation_namespace() -> None:
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

    assert '.ada-navigation__trigger--desktop {' in css
    assert 'position: absolute;' in css
    assert 'top: 50%;' in css
    assert 'inset-inline-end: 0;' in css
    assert 'transform: translateY(-50%);' in css
    assert 'border-radius: 0.75rem 0 0 0.75rem;' in css
    assert 'width: 1.25rem;' in css
    assert 'height: 2.1875rem;' in css
    assert '.ada-navigation__user {' in css
    assert 'flex-direction: column;' in css
    assert '.ada-navigation__avatar {' in css
    assert 'width: 5.75rem;' in css
    assert '.ada-navigation__action {' in css
    assert '.ada-navigation__offcanvas' in css
    assert 'background: var(--dark-color);' in css
    assert '.ada-navigation__brand-logo {' in css
    assert '.ada-navigation__main {' in css
    assert 'overflow-y: auto;' in css
    assert '.ada-navigation__footer {' in css
    assert '.ada-navigation__footer-logo {' in css
    assert '.ada-navigation__version {' in css
    assert '.dashboard-header-shell' not in css
    assert '.dashboard-menu-btn-desktop' not in css
