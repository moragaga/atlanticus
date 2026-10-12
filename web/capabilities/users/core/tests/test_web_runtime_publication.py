from __future__ import annotations

from types import SimpleNamespace

import atlanticus.web.users.web.callbacks as callbacks
from atlanticus.web.users.web.ids import managed_publish_id
from atlanticus.web.users.web.models import UsersAdminWebContext


class Administration:
    def __init__(self):
        self.calls = []

    def retry_runtime(self, user_id):
        self.calls.append(user_id)

    def discover(self):
        return SimpleNamespace(
            registry=SimpleNamespace(version='r1'),
            memberships=SimpleNamespace(version='m1'),
            profiles=(), candidates=(),
        )


class CallbackRegistry:
    def __init__(self):
        self.functions = {}

    def callback(self, *_args, **_kwargs):
        def register(fn):
            self.functions[fn.__name__] = fn
            return fn
        return register


def test_runtime_retry_calls_publication_not_user_update(monkeypatch):
    service = Administration()
    app = CallbackRegistry()
    callbacks.register_users_admin_callbacks(app, UsersAdminWebContext(administration=service))
    user_id = 'user:example'
    action_id = managed_publish_id(user_id)
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=action_id))
    snapshot = {'candidates': [{'user_id': user_id, 'state': 'promoted', 'runtime_status': 'missing'}]}
    fresh, notice = app.functions['retry_runtime_publication']([1], [action_id], snapshot)
    assert service.calls == [user_id]
    assert fresh['membership_version'] == 'm1'
    assert 'publicado' in notice.children


def test_runtime_retry_refuses_guest_candidate(monkeypatch):
    service = Administration()
    app = CallbackRegistry()
    callbacks.register_users_admin_callbacks(app, UsersAdminWebContext(administration=service))
    user_id = 'user:example'
    action_id = managed_publish_id(user_id)
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id=action_id))
    snapshot = {'candidates': [{'user_id': user_id, 'state': 'promotable', 'runtime_status': 'missing'}]}
    fresh, error = app.functions['retry_runtime_publication']([1], [action_id], snapshot)
    assert fresh is callbacks.no_update
    assert service.calls == []
    assert 'Refresh Users' in error.children
