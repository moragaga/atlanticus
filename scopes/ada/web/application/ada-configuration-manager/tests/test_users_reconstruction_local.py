from __future__ import annotations

from dataclasses import replace

from ada.web.application.configuration_manager.local_runtime import (
    InProcessUsersRuntimeStore,
    create_local_configuration_manager_stores,
)
from ada.web.application.configuration_manager.wiring import compose_configuration_manager_dependencies
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity, ToolUserMembership


class FakeDash:
    def __init__(self):
        self.callbacks = []

    def callback(self, *args, **kwargs):
        def decorate(fn):
            self.callbacks.append(fn)
            return fn
        return decorate


def _user():
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id='alice'),
        issuer='issuer', subject_id='alice', display_name='Alice',
    )
    return RuntimeUser(
        identity=identity, enabled=True, profile=RuntimeProfile.from_profile(BASIC_PROFILE),
        access_keys=('dashboard.view',),
    )


def test_local_base_publication_preserves_access_keys():
    initial = _user()
    store = InProcessUsersRuntimeStore((initial,))
    updated = replace(initial, profile=RuntimeProfile.from_profile(ROOT_PROFILE), access_keys=())
    actual = store.upsert_base_user(updated)
    assert actual.profile == updated.profile
    assert actual.access_keys == initial.access_keys
    assert store.list_users() == (actual,)


def test_local_manager_exposes_reconstruction_and_can_publish(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path)
    user = _user()
    stores.users_registry.replace((user.identity,), expected_version=None)
    stores.users_memberships.replace(
        (ToolUserMembership(
            user_id=user.user_id, profile_key='basic', enabled=True,
        ),),
        expected_version=None,
    )
    principal = ManagerPrincipal(
        subject_id='local', display_name='Local', profile_keys=('local',),
        administrative_override=True, is_local=True,
    )
    dependencies = compose_configuration_manager_dependencies(
        stores=stores, principal_provider=lambda: principal,
    )
    entry = dependencies.users_projection_entry
    assert entry is not None and entry.route == '/users-projection'
    entry.layout(None)
    app = FakeDash()
    entry.web_module.register_callbacks(app, None)
    _message, inspection = app.callbacks[0](1)
    assert inspection['create_ids'] == [user.user_id]
    _message, reset = app.callbacks[1](1, inspection, ['confirmed'])
    assert reset is None
    published = next(item for item in stores.users_runtime.list_users() if item.user_id == user.user_id)
    assert published.enabled is True
    assert published.profile.id == 'basic'
