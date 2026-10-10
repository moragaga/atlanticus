from __future__ import annotations

from types import SimpleNamespace

import atlanticus.web.users.web.callbacks as callbacks
from atlanticus.web.users.web.ids import candidate_profile_id, candidate_promote_id
from atlanticus.web.users.web.models import UsersAdminWebContext


class RecordingAdministration:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def discover(self):
        return SimpleNamespace(
            registry=SimpleNamespace(version='r1'),
            memberships=SimpleNamespace(version='m1'),
            profiles=(),
            candidates=(),
        )

    def promote(self, user_id, **kwargs):
        self.calls.append(('promote', user_id, kwargs))

    def update(self, user_id, **kwargs):
        self.calls.append(('update', user_id, kwargs))


class CallbackRegistry:
    def __init__(self) -> None:
        self.functions = {}

    def callback(self, *_args, **_kwargs):
        def register(callback):
            self.functions[callback.__name__] = callback
            return callback
        return register


def _callbacks():
    administration = RecordingAdministration()
    app = CallbackRegistry()
    callbacks.register_users_admin_callbacks(
        app,
        UsersAdminWebContext(administration=administration),
    )
    return administration, app.functions


def test_promote_forwards_snapshot_membership_version(monkeypatch):
    administration, registered = _callbacks()
    user = 'user:example'
    promote_id = candidate_promote_id(user)
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=promote_id))
    fresh, _message = registered['promote_user'](
        [1],
        [promote_id],
        ['basic'],
        [candidate_profile_id(user)],
        {'registry_version': 'r1', 'membership_version': 'm1'},
    )
    assert fresh['membership_version'] == 'm1'
    assert administration.calls == [
        ('promote', user, {
            'profile_key': 'basic',
            'enabled': True,
            'expected_registry_version': 'r1',
            'expected_membership_version': 'm1',
        })
    ]


def test_edit_forwards_membership_version_not_registry_version():
    administration, registered = _callbacks()
    fresh, _modal, _message = registered['save_user'](
        1,
        'user:example',
        'basic',
        ['enabled'],
        {'registry_version': 'r9', 'membership_version': 'm1'},
    )
    assert fresh['membership_version'] == 'm1'
    assert administration.calls == [
        ('update', 'user:example', {
            'profile_key': 'basic',
            'enabled': True,
            'expected_membership_version': 'm1',
        })
    ]


def test_edit_without_membership_version_does_not_write():
    administration, registered = _callbacks()
    result, _modal, message = registered['save_user'](
        1,
        'user:example',
        'basic',
        [],
        {'registry_version': 'r1'},
    )
    assert result is callbacks.no_update
    assert 'Refresh before saving' in message.children
    assert administration.calls == []


def test_promotion_allows_explicit_none_membership_version(monkeypatch):
    administration, registered = _callbacks()
    user = 'user:example'
    promote_id = candidate_promote_id(user)
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=promote_id))
    registered['promote_user'](
        [1],
        [promote_id],
        ['basic'],
        [candidate_profile_id(user)],
        {'registry_version': None, 'membership_version': None},
    )
    assert administration.calls[0][2]['expected_membership_version'] is None
