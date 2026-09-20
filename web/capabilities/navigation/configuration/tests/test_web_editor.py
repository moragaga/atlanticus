import pytest

from atlanticus.web.navigation.configuration.editor import (
    build_initial_catalog,
    create_group,
    remove_group,
    reorder_link,
    reorder_root_node,
    upsert_link,
)
from atlanticus.web.navigation.configuration.profiles import (
    NavigationProfileOption,
    profile_options,
)


def test_navigation_profile_options_are_empty_without_provider() -> None:
    assert profile_options() == ()


def test_navigation_profile_options_come_from_composition_provider() -> None:
    options = (
        NavigationProfileOption('guest', 'Guest'),
        NavigationProfileOption('operator', 'Operator'),
    )

    assert profile_options(lambda: options) == options


def test_navigation_profile_options_provider_errors_propagate() -> None:
    def provider() -> tuple[NavigationProfileOption, ...]:
        raise RuntimeError('profile options unavailable')

    with pytest.raises(RuntimeError, match='profile options unavailable'):
        profile_options(provider)

def test_editor_starts_empty_and_allows_empty_sections() -> None:
    catalog = build_initial_catalog()

    assert catalog.links == ()
    assert catalog.groups == ()

    catalog = create_group(catalog, label='Procesos', icon=None, enabled=True)

    assert catalog.groups[0].key == 'procesos'
    assert catalog.groups[0].links == ()


def test_link_can_move_between_root_and_sections_without_losing_access() -> None:
    catalog = create_group(
        build_initial_catalog(),
        label='Procesos',
        icon=None,
        enabled=True,
    )
    catalog = upsert_link(
        catalog,
        editor_key=None,
        parent_group_key=None,
        label='Operación',
        href='/operation',
        icon=None,
        enabled=True,
        new_tab=False,
        force_reload=False,
        allowed_profiles=('guest', 'operador'),
    )
    key = catalog.links[0].key

    grouped = upsert_link(
        catalog,
        editor_key=key,
        parent_group_key='procesos',
        label='Operación',
        href='/operation',
        icon=None,
        enabled=True,
        new_tab=False,
        force_reload=False,
        allowed_profiles=('guest', 'operador'),
    )

    assert grouped.links == ()
    assert grouped.groups[0].links[0].allowed_profiles == ('guest', 'operador')

    restored = upsert_link(
        grouped,
        editor_key=key,
        parent_group_key=None,
        label='Operación',
        href='/operation',
        icon=None,
        enabled=True,
        new_tab=False,
        force_reload=False,
        allowed_profiles=('guest', 'operador'),
    )

    assert restored.groups[0].links == ()
    assert restored.links[0].allowed_profiles == ('guest', 'operador')


def test_removing_section_moves_its_links_to_root() -> None:
    catalog = create_group(
        build_initial_catalog(),
        label='Procesos',
        icon=None,
        enabled=True,
    )
    catalog = upsert_link(
        catalog,
        editor_key=None,
        parent_group_key='procesos',
        label='Operación',
        href='/operation',
        icon=None,
        enabled=True,
        new_tab=False,
        force_reload=False,
        allowed_profiles=('guest',),
    )

    restored = remove_group(catalog, key='procesos')

    assert restored.groups == ()
    assert restored.links[0].key == 'operacion'
    assert restored.links[0].allowed_profiles == ('guest',)


def test_top_level_and_section_links_have_independent_ordering() -> None:
    catalog = build_initial_catalog()
    catalog = upsert_link(
        catalog,
        editor_key=None,
        parent_group_key=None,
        label='Primero',
        href='/first',
        icon=None,
        enabled=True,
        new_tab=False,
        force_reload=False,
        allowed_profiles=('guest',),
    )
    catalog = create_group(catalog, label='Grupo', icon=None, enabled=True)
    catalog = reorder_root_node(catalog, key='grupo', direction=-1)

    assert catalog.groups[0].order == 10
    assert catalog.links[0].order == 20

    catalog = upsert_link(
        catalog,
        editor_key=None,
        parent_group_key='grupo',
        label='Uno',
        href='/one',
        icon=None,
        enabled=True,
        new_tab=False,
        force_reload=False,
        allowed_profiles=('guest',),
    )
    catalog = upsert_link(
        catalog,
        editor_key=None,
        parent_group_key='grupo',
        label='Dos',
        href='/two',
        icon=None,
        enabled=True,
        new_tab=False,
        force_reload=False,
        allowed_profiles=('guest',),
    )
    catalog = reorder_link(catalog, key='dos', direction=-1)

    assert [link.key for link in catalog.groups[0].links] == ['dos', 'uno']
