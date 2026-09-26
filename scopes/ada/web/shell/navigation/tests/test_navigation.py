import pytest

from ada.web.shell.navigation import (
    ADA_NAVIGATION_ASSET_LAYER,
    AdaNavigationAction,
    AdaNavigationView,
    build_ada_navigation_controller,
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


def test_desktop_trigger_contract_is_preserved() -> None:
    trigger = build_ada_navigation_desktop_trigger()
    props = trigger.to_plotly_json()['props']

    assert props['id'] == 'ada-navigation-desktop-toggle'
    assert props['n_clicks'] == 0
    assert 'title' not in props
    assert any(
        child.to_plotly_json()['props'].get('className') == 'visually-hidden'
        and child.children == 'Abrir navegación'
        for child in trigger.children
    )


def test_mobile_trigger_contract_is_preserved() -> None:
    trigger = build_ada_navigation_mobile_trigger()
    props = trigger.to_plotly_json()['props']

    assert props['id'] == 'ada-navigation-mobile-toggle'
    assert props['n_clicks'] == 0
    assert 'title' not in props
    assert any(
        child.to_plotly_json()['props'].get('className') == 'visually-hidden'
        and child.children == 'Abrir navegación'
        for child in trigger.children
    )


def test_navigation_controller_is_always_mounted_independently_from_offcanvas() -> None:
    controller = build_ada_navigation_controller()
    assert controller.id == 'ada-navigation-controller'
    assert tuple(child.id for child in controller.children) == (
        'ada-navigation-location',
        'ada-navigation-last-path',
    )
    assert controller.children[0].refresh is False
    assert controller.children[1].data is None
    offcanvas = build_ada_navigation_offcanvas(_menu())
    assert all(child.id != 'ada-navigation-location' for child in offcanvas.children)


def test_offcanvas_preserves_navigation_contract_with_injected_view() -> None:
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

    def walk(value: object):
        yield value
        children = getattr(value, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from walk(child)
        elif children is not None and not isinstance(children, (str, int, float, bool)):
            yield from walk(children)

    nodes = tuple(walk(component))
    route_groups = next(
        node for node in nodes if getattr(node, 'id', None) == 'ada-navigation-route-groups'
    )
    slot_keys = {
        node.to_plotly_json()['props'].get('data-ada-slot-key')
        for node in nodes
        if hasattr(node, 'to_plotly_json')
    }

    assert component.id == 'ada-navigation-offcanvas'
    assert component.is_open is False
    assert {'navigation_identity', 'navigation_scroll', 'navigation_footer'} <= slot_keys
    assert route_groups.data == {'/status': 'configuration'}
    assert '/' not in route_groups.data
    assert 'Local User' in payload
    assert '/assets/ada/logo.svg' in payload
    assert 'Asistente de Decisiones Ágiles' in payload
    assert '/assets/ada/pelambres.svg' in payload
    assert 'Versión 0.1.5' in payload


def test_user_card_preserves_user_information() -> None:
    payload = str(build_ada_navigation_offcanvas(_menu()).to_plotly_json())

    assert 'Local User' in payload
    assert 'local@example.com' in payload
    assert 'LU' in payload


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
    assert 'https://example.test/ada' not in without_action
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


