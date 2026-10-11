from __future__ import annotations

from dataclasses import replace

from atlanticus.web.profiles.models import BASIC_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.reconstruction import UsersReconstructionPreview
from atlanticus.web.users.web.reconstruction import (
    UsersReconstructionWebContext,
    inspection_document,
    register_users_reconstruction_callbacks,
)


class FakeDash:
    def __init__(self):
        self.callbacks = []

    def callback(self, *args, **kwargs):
        def decorate(fn):
            self.callbacks.append(fn)
            return fn
        return decorate


class Workflow:
    def __init__(self, preview):
        self.preview = preview
        self.applied = []

    def inspect(self):
        return self.preview

    def apply(self, preview):
        self.applied.append(preview)


def _preview():
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id='alice'),
        issuer='issuer', subject_id='alice', display_name='Alice',
    )
    user = RuntimeUser(
        identity=identity, enabled=True, profile=RuntimeProfile.from_profile(BASIC_PROFILE),
    )
    return UsersReconstructionPreview(
        desired_users=(user,), create_ids=(user.user_id,), update_ids=(), disable_ids=(),
    )


def test_inspect_and_apply_use_revalidated_server_state():
    workflow = Workflow(_preview())
    app = FakeDash()
    register_users_reconstruction_callbacks(
        app, UsersReconstructionWebContext(workflow=workflow, can_manage=lambda: True)
    )
    assert len(app.callbacks) == 2
    _message, inspection = app.callbacks[0](1)
    assert inspection['create_ids'] == [workflow.preview.desired_users[0].user_id]
    _message, reset = app.callbacks[1](1, inspection, ['confirmed'])
    assert reset is None
    assert workflow.applied == [workflow.preview]


def test_apply_rejects_changed_desired_user_even_with_same_ids():
    workflow = Workflow(_preview())
    app = FakeDash()
    register_users_reconstruction_callbacks(
        app, UsersReconstructionWebContext(workflow=workflow, can_manage=lambda: True)
    )
    _message, inspection = app.callbacks[0](1)
    user = workflow.preview.desired_users[0]
    workflow.preview = replace(
        workflow.preview, desired_users=(replace(user, enabled=False),)
    )
    message, reset = app.callbacks[1](1, inspection, ['confirmed'])
    assert 'changed' in str(message.children).lower()
    assert reset is None
    assert workflow.applied == []


def test_inspection_fingerprint_ignores_browser_supplied_payload():
    document = inspection_document(_preview())
    assert set(document) == {'fingerprint', 'create_ids', 'update_ids', 'disable_ids'}
    assert len(document['fingerprint']) == 64
