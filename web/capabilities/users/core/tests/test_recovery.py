from datetime import UTC, datetime

import pytest

from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.recovery import (
    ToolUsersRecoveryService,
    ToolUsersRecoverySnapshot,
    UsersRecoveryConflictError,
)
from atlanticus.web.users.store import UsersRuntimeStore


def runtime_user(subject='subject-1', *, root=False):
    issuer = 'issuer'
    identity = UserIdentity(
        user_id=build_user_key(issuer=issuer, subject_id=subject),
        issuer=issuer,
        subject_id=subject,
        display_name=f'User {subject}',
    )
    return RuntimeUser(
        identity=identity,
        enabled=True,
        profile=RuntimeProfile.from_profile(ROOT_PROFILE if root else BASIC_PROFILE),
    )


class RuntimeStore(UsersRuntimeStore):
    def __init__(self, users=()):
        self.users = {user.user_id: user for user in users}

    def resolve(self, identity: AuthenticatedIdentity):
        return next(
            (
                user
                for user in self.users.values()
                if user.issuer == identity.issuer and user.subject_id == identity.subject_id
            ),
            None,
        )

    def list_users(self):
        return tuple(sorted(self.users.values(), key=lambda user: user.user_id))

    def replace_all(self, users):
        self.users = {user.user_id: user for user in users}
        return self.list_users()


class Snapshots:
    def __init__(self):
        self.items = {}

    def list_snapshot_ids(self, *, max_items=200):
        return tuple(self.items)

    def list_snapshot_summaries(self, *, max_items=200):
        return tuple((key, None) for key in self.items)

    def save(self, snapshot):
        if snapshot.snapshot_id in self.items:
            raise AssertionError('duplicate snapshot')
        self.items[snapshot.snapshot_id] = snapshot

    def load(self, snapshot_id):
        return self.items[snapshot_id]


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event):
        self.events.append(event)


class BeforeImages:
    def __init__(self):
        self.images = []

    def save(self, image):
        self.images.append(image)


def service(*, runtime=None, materialize=()):
    snapshots = Snapshots()
    audit = Audit()
    before = BeforeImages()
    svc = ToolUsersRecoveryService(
        runtime=runtime or RuntimeStore(),
        materialize=lambda: tuple(materialize),
        snapshots=snapshots,
        audit=audit,
        before_images=before,
        environment='local:test',
    )
    return svc, snapshots, audit, before


def capture(svc):
    preview = svc.preview_capture()
    return svc.capture(
        preview=preview,
        approved_user_ids=tuple(user.user_id for user in preview.users),
        operator_id='operator',
        approval_reference='ticket-1',
        confirmed=True,
    )


def test_capture_is_complete_tool_runtime_snapshot():
    users = (runtime_user('a'), runtime_user('b', root=True))
    svc, snapshots, _audit, _before = service(materialize=users)
    preview = svc.preview_capture()
    assert preview.users == tuple(sorted(users, key=lambda user: user.user_id))
    snapshot = capture(svc)
    assert snapshots.load(snapshot.snapshot_id) == snapshot
    assert ToolUsersRecoverySnapshot.from_document(snapshot.to_document()) == snapshot


def test_capture_rejects_partial_user_selection():
    users = (runtime_user('a'), runtime_user('b'))
    svc, _snapshots, _audit, _before = service(materialize=users)
    preview = svc.preview_capture()
    with pytest.raises(UsersRecoveryConflictError):
        svc.capture(
            preview=preview,
            approved_user_ids=(users[0].user_id,),
            operator_id='operator',
            approval_reference='ticket',
            confirmed=True,
        )


def test_validate_and_replace_align_users_runtime_destructively():
    desired = (runtime_user('a'), runtime_user('b', root=True))
    current = (runtime_user('a', root=True), runtime_user('obsolete'))
    runtime = RuntimeStore(current)
    svc, _snapshots, audit, before = service(runtime=runtime, materialize=desired)
    snapshot = capture(svc)
    validation = svc.validate_replace(snapshot.snapshot_id)
    assert set(validation.create_ids) == {desired[1].user_id}
    assert set(validation.update_ids) == {desired[0].user_id}
    assert set(validation.delete_ids) == {current[1].user_id}

    after = svc.replace_snapshot(
        snapshot_id=snapshot.snapshot_id,
        operator_id='operator',
        approval_reference='ticket-2',
        confirmed=True,
        maintenance_confirmed=True,
        revocations_reviewed=True,
    )
    assert after.differences == ()
    assert runtime.list_users() == tuple(sorted(desired, key=lambda user: user.user_id))
    assert len(before.images) == 1
    assert [event.stage for event in audit.events] == ['started', 'completed']


def test_snapshot_document_does_not_repeat_storage_scope():
    svc, _snapshots, _audit, _before = service(materialize=(runtime_user('a'),))
    snapshot = capture(svc)
    document = snapshot.to_document()
    assert 'application_key' not in document
    assert 'tool_key' not in document
