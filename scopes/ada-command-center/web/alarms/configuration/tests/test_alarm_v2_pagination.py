from types import SimpleNamespace

import pytest

from ada_command_center.web.alarms.configuration.web import family_callbacks
from ada_command_center.web.alarms.configuration.web.families import initial_navigation
from ada_command_center.web.alarms.configuration.web.ids import (
    LIST_PAGE_SIZE_TYPE,
    LIST_PAGE_TYPE,
)
from ada_command_center.web.alarms.configuration.web.pagination import (
    change_list_page,
    list_page,
    page_tokens,
)


class CallbackApp:
    def __init__(self):
        self.callbacks = {}

    def callback(self, *_args, **_kwargs):
        def register(func):
            self.callbacks[func.__name__] = func
            return func

        return register


def test_pagination_keeps_independent_lists_and_original_indexes():
    navigation = initial_navigation()
    navigation = change_list_page(navigation, 'families', size=20)
    navigation = change_list_page(navigation, 'families', page=2)
    navigation = change_list_page(navigation, 'rules', page=3)
    assert list_page(tuple(range(34)), navigation, 'families').items == tuple(range(20, 34))
    assert list_page(tuple(range(45)), navigation, 'rules').items == tuple(range(20, 30))
    assert list_page(tuple(range(18)), navigation, 'messages').items == tuple(range(10))
    assert list_page(tuple(range(18)), navigation, 'global').items == tuple(range(10))
    assert list_page((), navigation, 'rules').request.page_number == 1


def test_page_size_change_resets_only_its_list():
    original = change_list_page(initial_navigation(), 'global', page=5)
    original = change_list_page(original, 'families', page=2)
    changed = change_list_page(original, 'global', size=20)
    assert changed['pagination']['global'] == {'page': 1, 'size': 20}
    assert changed['pagination']['families']['page'] == 2
    assert original['pagination']['global']['page'] == 5
    assert page_tokens(5, 12) == (1, None, 4, 5, 6, None, 12)


@pytest.mark.parametrize('size', [1, 11, 50, True])
def test_page_size_is_limited_to_atlanticus_contract(size):
    with pytest.raises(ValueError):
        change_list_page(initial_navigation(), 'families', size=size)


def test_pagination_callback_preserves_current_family_and_draft(monkeypatch):
    app = CallbackApp()
    family_callbacks.register_family_callbacks(app)
    navigation = {
        **initial_navigation(),
        'page': 'family',
        'family_key': 'mina',
        'pending_families': ['mina'],
    }
    monkeypatch.setattr(
        family_callbacks,
        'ctx',
        SimpleNamespace(
            triggered_id={'type': LIST_PAGE_TYPE, 'listing': 'rules', 'page': 2, 'action': 'page'},
            triggered=[{'value': 1}],
        ),
    )
    updated = app.callbacks['change_pagination']([1], [], navigation)
    assert updated['page'] == 'family'
    assert updated['pending_families'] == ['mina']
    assert updated['pagination']['rules']['page'] == 2
    monkeypatch.setattr(
        family_callbacks,
        'ctx',
        SimpleNamespace(
            triggered_id={'type': LIST_PAGE_SIZE_TYPE, 'listing': 'rules', 'size': 20},
            triggered=[{'value': 1}],
        ),
    )
    resized = app.callbacks['change_pagination']([], [1], updated)
    assert resized['pagination']['rules'] == {'page': 1, 'size': 20}


def test_pagination_button_ids_do_not_repeat_for_arrows_and_page_numbers():
    from dash import html

    from ada_command_center.web.alarms.configuration.web.pagination import list_pagination

    page = list_page(tuple(range(25)), initial_navigation(), 'rules')
    rendered = list_pagination(page, 'rules')
    controls = rendered.children[1].children
    ids = [str(item.id) for item in controls if isinstance(item, html.Button)]
    assert len(ids) == len(set(ids))
