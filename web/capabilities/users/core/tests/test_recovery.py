from __future__ import annotations

from dataclasses import replace

import pytest

from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.users.errors import UserAlreadyPromotedError, UsersRegistryConflictError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import UserRecord, UsersRegistrySnapshot
from atlanticus.web.users.recovery import (
    ApprovedUsersSnapshot,
    RegistryRecoveryState,
    UserDifferenceKind,
    UsersApprovedRecoveryService,
    UsersRecoveryConflictError,
    UsersReplaceBeforeImage,
    VersionedUser,
)
from atlanticus.web.users.store import UsersAdministrationStore, UsersRegistryStore

CUSTOM = '11111111-1111-4111-8111-111111111111'


def user(subject: str, *, profile_key: str = 'basic', enabled: bool = True) -> UserRecord:
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id=subject),
        issuer='entra',
        subject_id=subject,
        display_name=f'User {subject}',
        email=f'{subject}@example.com',
        enabled=enabled,
        profile_key=profile_key,
    )


class MemoryRegistry(UsersRegistryStore):
    def __init__(self, users=(), version=None):
        self.snapshot = UsersRegistrySnapshot(users=tuple(users), version=version)
        self.replaces = 0

    def load(self):
        return self.snapshot

    def replace(self, users, *, expected_version):
        if expected_version != self.snapshot.version:
            raise UsersRegistryConflictError('Users registry changed concurrently')
        self.replaces += 1
        self.snapshot = UsersRegistrySnapshot(users=users, version=f'v{self.replaces}')
        return self.snapshot


class MemoryPromoted(UsersAdministrationStore):
    def __init__(self, users=()):
        self.users = {value.user_id: value for value in users}
        self.creates = 0
        self.fail_after = None
        self.versions = {value.user_id: 'v1' for value in users}
        self.fail_delete_after = None
        self.deletes = 0

    def get(self, user_id):
        return self.users.get(user_id)

    def list_users(self):
        return tuple(self.users.values())

    def create(self, value):
        if value.user_id in self.users:
            raise UserAlreadyPromotedError('User is already promoted')
        if self.fail_after is not None and self.creates >= self.fail_after:
            raise RuntimeError('Simulated Cosmos outage')
        self.users[value.user_id] = value
        self.versions[value.user_id] = 'v1'
        self.creates += 1
        return value

    def replace(self, user):
        self.users[user.user_id] = user
        self.versions[user.user_id] = 'v2'
        return user

    def list_versioned_users(self):
        return tuple(
            VersionedUser(user=user, version=self.versions[user.user_id])
            for user in self.users.values()
        )

    def replace_if_version(self, user, *, expected_version):
        if self.versions.get(user.user_id) != expected_version:
            raise RuntimeError('Concurrent user change')
        return self.replace(user)

    def delete_if_version(self, user_id, *, expected_version):
        if self.versions.get(user_id) != expected_version:
            raise RuntimeError('Concurrent user change')
        if self.fail_delete_after is not None and self.deletes >= self.fail_delete_after:
            raise RuntimeError('Simulated delete outage')
        del self.users[user_id]
        del self.versions[user_id]
        self.deletes += 1


class MemorySnapshots:
    def __init__(self):
        self.items = {}

    def save(self, snapshot):
        if snapshot.snapshot_id in self.items:
            raise UsersRecoveryConflictError('Snapshot already exists')
        self.items[snapshot.snapshot_id] = snapshot

    def load(self, snapshot_id):
        return self.items[snapshot_id]


class MemoryAudit:
    def __init__(self):
        self.events = {}
        self.available = True

    def record(self, event):
        if not self.available:
            raise RuntimeError('Simulated audit outage')
        key = event.operation_id, event.stage
        if key in self.events:
            raise UsersRecoveryConflictError('Audit event already exists')
        self.events[key] = event


class MemoryBeforeImages:
    def __init__(self):
        self.images = {}
        self.available = True

    def save(self, image):
        if not self.available:
            raise RuntimeError('Before-image unavailable')
        if image.operation_id in self.images:
            raise RuntimeError('Before-image already exists')
        self.images[image.operation_id] = image


def profiles(with_custom=True):
    return ProfileCatalog(
        profiles=(
            (ProfileDefinition(key=CUSTOM, label='Analyst', background_color='#112233'),)
            if with_custom else ()
        )
    )


def service(registry=None, promoted=None, snapshots=None, audit=None, *, realm='tenant-1', catalog=None):
    return UsersApprovedRecoveryService(
        registry=registry if registry is not None else MemoryRegistry(),
        promoted=promoted if promoted is not None else MemoryPromoted(),
        profiles=(lambda: catalog if catalog is not None else profiles()),
        snapshots=snapshots if snapshots is not None else MemorySnapshots(),
        audit=audit if audit is not None else MemoryAudit(),
        application_key='ada-generic',
        identity_realm=realm,
        environment='DEV',
    )


def capture(approved_users, *, candidates=()):
    snapshots = MemorySnapshots()
    source = service(
        registry=MemoryRegistry((*approved_users, *candidates), version='v1'),
        promoted=MemoryPromoted(approved_users),
        snapshots=snapshots,
    )
    preview = source.preview_capture()
    snapshot = source.capture(
        preview=preview,
        approved_user_ids=tuple(value.user_id for value in approved_users),
        operator_id='operator',
        approval_reference='change-123',
        confirmed=True,
    )
    return preview, snapshot, snapshots


def restore(svc, report, *, operation_id='restore-1'):
    return svc.restore(
        validation=report,
        confirmed_digest=report.snapshot.content_digest,
        operator_id='operator',
        approval_reference='restore-ticket',
        operation_id=operation_id,
        confirmed=True,
        maintenance_confirmed=True,
    )


def test_capture_requires_exact_registry_match_and_ignores_candidates():
    managed = user('approved')
    pending = user('pending', profile_key='guest', enabled=False)
    preview, snapshot, snapshots = capture((managed,), candidates=(pending,))
    assert preview.candidate_user_ids == (pending.user_id,)
    assert snapshot.users == (managed,)
    assert snapshots.load(snapshot.snapshot_id) is snapshot
    assert ApprovedUsersSnapshot.from_document(snapshot.to_document()) == snapshot


def test_capture_fails_for_divergent_or_unapproved_promotions():
    managed = user('approved')
    source = service(
        registry=MemoryRegistry((replace(managed, enabled=False),), version='v1'),
        promoted=MemoryPromoted((managed,)),
    )
    with pytest.raises(UsersRecoveryConflictError, match='differs'):
        source.preview_capture()
    guest = user('guest', profile_key='guest')
    source = service(
        registry=MemoryRegistry((guest,), version='v1'),
        promoted=MemoryPromoted((guest,)),
    )
    with pytest.raises(UsersRecoveryConflictError, match='profile'):
        source.preview_capture()


def test_capture_requires_current_preview_selected_ids_and_confirmation():
    managed = user('approved')
    registry = MemoryRegistry((managed,), version='v1')
    source = service(registry=registry, promoted=MemoryPromoted((managed,)))
    preview = source.preview_capture()
    params = dict(
        preview=preview,
        approved_user_ids=(managed.user_id,),
        operator_id='operator',
        approval_reference='change',
    )
    with pytest.raises(UsersRecoveryConflictError, match='confirmation'):
        source.capture(**params, confirmed=False)
    with pytest.raises(UsersRecoveryConflictError, match='Selected'):
        source.capture(**{**params, 'approved_user_ids': ()}, confirmed=True)
    registry.snapshot = replace(registry.snapshot, version='v2')
    with pytest.raises(UsersRecoveryConflictError, match='outdated'):
        source.capture(**params, confirmed=True)


def test_empty_target_restores_only_approved_users_and_audits():
    approved = (user('one'), user('two', enabled=False))
    _, snapshot, snapshots = capture(approved, candidates=(user('guest', profile_key='guest'),))
    registry, promoted, audit = MemoryRegistry(), MemoryPromoted(), MemoryAudit()
    target = service(registry, promoted, snapshots, audit)
    report = target.validate(snapshot.snapshot_id)
    assert report.registry_state is RegistryRecoveryState.EMPTY
    assert {difference.kind for difference in report.differences} == {UserDifferenceKind.MISSING}
    assert report.can_restore
    after = restore(target, report)
    assert after.registry_state is RegistryRecoveryState.MATCH
    assert not after.differences
    assert registry.snapshot.users == tuple(sorted(approved, key=lambda value: value.user_id))
    assert set(promoted.users) == {value.user_id for value in approved}
    assert set(audit.events) == {('restore-1', 'started'), ('restore-1', 'completed')}
    assert registry.replaces == 1
    assert promoted.creates == 2
    assert restore(target, target.validate(snapshot.snapshot_id), operation_id='restore-2') == after
    assert registry.replaces == 1
    assert promoted.creates == 2


def test_restore_rejects_unexpected_users_and_modified_profiles():
    approved = user('one')
    _, snapshot, snapshots = capture((approved,))
    unexpected = user('outsider')
    untouched_registry = MemoryRegistry()
    target = service(untouched_registry, MemoryPromoted((unexpected,)), snapshots)
    report = target.validate(snapshot.snapshot_id)
    assert UserDifferenceKind.UNEXPECTED in {difference.kind for difference in report.differences}
    assert not report.can_restore
    with pytest.raises(UsersRecoveryConflictError, match='not empty'):
        restore(target, report)
    assert untouched_registry.replaces == 0
    target = service(
        MemoryRegistry((approved,), version='v1'),
        MemoryPromoted((replace(approved, profile_key='root'),)),
        snapshots,
    )
    report = target.validate(snapshot.snapshot_id)
    difference = next(item for item in report.differences if item.kind is UserDifferenceKind.DIFFERENT)
    assert difference.fields == ('profile_key',)
    assert not report.can_restore


def test_restore_rejects_registry_candidates_even_when_cosmos_is_empty():
    approved = user('one')
    _, snapshot, snapshots = capture((approved,))
    target_registry = MemoryRegistry((user('pending', profile_key='guest'),), version='v1')
    target = service(target_registry, MemoryPromoted(), snapshots)
    report = target.validate(snapshot.snapshot_id)
    assert report.registry_state is RegistryRecoveryState.CONFLICT
    assert not report.can_restore
    with pytest.raises(UsersRecoveryConflictError):
        restore(target, report)
    assert target_registry.replaces == 0


def test_restore_blocks_unavailable_profiles_and_different_identity_realm():
    approved = user('one', profile_key=CUSTOM)
    _, snapshot, snapshots = capture((approved,))
    target = service(snapshots=snapshots, catalog=profiles(with_custom=False))
    report = target.validate(snapshot.snapshot_id)
    assert UserDifferenceKind.PROFILE_UNAVAILABLE in {item.kind for item in report.differences}
    assert not report.can_restore
    with pytest.raises(UsersRecoveryConflictError, match='identity realm'):
        service(snapshots=snapshots, realm='tenant-other').validate(snapshot.snapshot_id)


def test_partial_failure_can_retry_without_reapproving_users():
    approved = (user('one'), user('two'))
    _, snapshot, snapshots = capture(approved)
    target_registry, promoted, audit = MemoryRegistry(), MemoryPromoted(), MemoryAudit()
    promoted.fail_after = 1
    target = service(target_registry, promoted, snapshots, audit)
    with pytest.raises(RuntimeError, match='outage'):
        restore(target, target.validate(snapshot.snapshot_id))
    assert target_registry.snapshot.users == tuple(sorted(approved, key=lambda value: value.user_id))
    assert promoted.creates == 1
    assert ('restore-1', 'failed') in audit.events
    promoted.fail_after = None
    report = target.validate(snapshot.snapshot_id)
    assert report.can_restore
    result = restore(target, report, operation_id='restore-2')
    assert not result.differences
    assert target_registry.replaces == 1
    assert promoted.creates == 2


def test_restore_detects_changed_validation_or_denied_audit_before_mutation():
    approved = user('one')
    _, snapshot, snapshots = capture((approved,))
    registry, promoted, audit = MemoryRegistry(), MemoryPromoted(), MemoryAudit()
    target = service(registry, promoted, snapshots, audit)
    report = target.validate(snapshot.snapshot_id)
    registry.snapshot = replace(registry.snapshot, version='external')
    with pytest.raises(UsersRecoveryConflictError, match='changed'):
        restore(target, report)
    assert not audit.events
    report = target.validate(snapshot.snapshot_id)
    audit.available = False
    with pytest.raises(RuntimeError, match='audit'):
        restore(target, report)
    assert not promoted.users
    assert registry.replaces == 0


def test_snapshot_detects_tampered_data_and_rejects_guest():
    _, snapshot, _ = capture((user('one'),))
    payload = snapshot.to_document()
    payload['users'][0]['profile_key'] = 'root'
    with pytest.raises(ValueError, match='snapshot document is invalid'):
        ApprovedUsersSnapshot.from_document(payload)
    payload = snapshot.to_document()
    payload['users'][0]['profile_key'] = 'guest'
    with pytest.raises(ValueError, match='snapshot document is invalid'):
        ApprovedUsersSnapshot.from_document(payload)


def test_registry_conflict_reports_missing_and_unexpected_ids():
    source_user = user('source')
    _, snapshot, snapshots = capture((source_user,))
    target_user = user('unexpected')
    target = service(
        registry=MemoryRegistry((target_user,), version='v1'),
        promoted=MemoryPromoted(),
        snapshots=snapshots,
    )
    validation = target.validate(snapshot.snapshot_id)
    assert validation.registry_state is RegistryRecoveryState.CONFLICT
    assert set(validation.registry_conflict_user_ids) == {source_user.user_id, target_user.user_id}


def test_completion_audit_failure_remains_retryable_without_new_users():
    approved = user('one')
    _, snapshot, snapshots = capture((approved,))
    registry, promoted = MemoryRegistry(), MemoryPromoted()

    class FailedCompletion(MemoryAudit):
        def record(self, event):
            if event.stage == 'completed':
                raise RuntimeError('Simulated completion audit outage')
            super().record(event)

    audit = FailedCompletion()
    target = service(registry, promoted, snapshots, audit)
    with pytest.raises(RuntimeError, match='completion audit'):
        restore(target, target.validate(snapshot.snapshot_id))
    assert ('restore-1', 'started') in audit.events
    assert ('restore-1', 'failed') in audit.events
    assert promoted.creates == 1
    assert target.validate(snapshot.snapshot_id).can_restore
    restore(service(registry, promoted, snapshots, MemoryAudit()), target.validate(snapshot.snapshot_id), operation_id='restore-2')
    assert promoted.creates == 1


def test_snapshot_metadata_is_protected_by_artifact_digest():
    _, snapshot, _ = capture((user('one'),))
    payload = snapshot.to_document()
    payload['operator_id'] = 'someone-else'
    with pytest.raises(ValueError, match='snapshot document is invalid'):
        ApprovedUsersSnapshot.from_document(payload)


def test_capture_does_not_need_audit_but_restore_requires_it():
    approved = user('one')
    snapshots = MemorySnapshots()
    origin = UsersApprovedRecoveryService(
        registry=MemoryRegistry((approved,), version='v1'),
        promoted=MemoryPromoted((approved,)),
        profiles=profiles,
        snapshots=snapshots,
        application_key='ada-generic',
        identity_realm='tenant-1',
        environment='DEV',
    )
    preview = origin.preview_capture()
    saved = origin.capture(
        preview=preview,
        approved_user_ids=(approved.user_id,),
        operator_id='operator',
        approval_reference='ticket',
        confirmed=True,
    )
    destination = UsersApprovedRecoveryService(
        registry=MemoryRegistry(),
        promoted=MemoryPromoted(),
        profiles=profiles,
        snapshots=snapshots,
        application_key='ada-generic',
        identity_realm='tenant-1',
        environment='UAT',
    )
    with pytest.raises(UsersRecoveryConflictError, match='audit store'):
        restore(destination, destination.validate(saved.snapshot_id))


def replacement_service(registry, promoted, snapshots, audit, before_images, *, catalog=None):
    return UsersApprovedRecoveryService(
        registry=registry,
        promoted=promoted,
        replace_store=promoted,
        profiles=lambda: catalog if catalog is not None else profiles(),
        snapshots=snapshots,
        audit=audit,
        before_images=before_images,
        application_key='ada-generic',
        identity_realm='tenant-1',
        environment='UAT',
    )


def execute_replace(service, validation, *, operation_id='replace-1', confirmed=True, maintenance=True, revocations=True):
    return service.replace_approved(
        validation=validation,
        confirmed_digest=validation.recovery.snapshot.content_digest,
        operator_id='operator',
        approval_reference='replace-ticket',
        operation_id=operation_id,
        confirmed=confirmed,
        maintenance_confirmed=maintenance,
        revocations_reviewed=revocations,
    )


def test_replace_reconciles_registry_candidates_and_cosmos_using_snapshot():
    source = (user('approved'), user('missing', enabled=False))
    _, snapshot, snapshots = capture(source)
    altered = replace(source[0], profile_key='root')
    unexpected = user('extra')
    candidate = user('candidate', profile_key='guest', enabled=False)
    registry = MemoryRegistry((altered, unexpected, candidate), version='v1')
    promoted = MemoryPromoted((altered, unexpected))
    audit, before = MemoryAudit(), MemoryBeforeImages()
    target = replacement_service(registry, promoted, snapshots, audit, before)
    validation = target.validate_replace(snapshot.snapshot_id)
    assert not validation.recovery.can_restore
    assert validation.can_replace
    assert validation.plan.registry_discarded_ids == (candidate.user_id, unexpected.user_id)
    assert validation.plan.update_ids == (source[0].user_id,)
    assert validation.plan.create_ids == (source[1].user_id,)
    assert validation.plan.delete_ids == (unexpected.user_id,)
    done = execute_replace(target, validation)
    assert done.recovery.registry_state is RegistryRecoveryState.MATCH
    assert not done.recovery.differences
    assert not done.plan.registry_write_required
    assert tuple(sorted(promoted.users)) == tuple(sorted(value.user_id for value in source))
    assert registry.snapshot.users == tuple(sorted(source, key=lambda record: record.user_id))
    assert registry.replaces == 1
    assert promoted.deletes == 1
    assert audit.events[('replace-1', 'completed')].to_document()['schema_version'] == 2
    assert audit.events[('replace-1', 'completed')].updated_user_ids == (source[0].user_id,)
    assert audit.events[('replace-1', 'completed')].deleted_user_ids == (unexpected.user_id,)
    image = before.images['replace-1']
    assert image.registry_users == tuple(sorted((altered, unexpected, candidate), key=lambda record: record.user_id))
    assert image.promoted_users == tuple(sorted((altered, unexpected), key=lambda record: record.user_id))
    assert UsersReplaceBeforeImage.from_document(image.to_document()) == image
    document = image.to_document()
    document['promoted_users'][0]['profile_key'] = 'basic'
    with pytest.raises(ValueError, match='before-image'):
        UsersReplaceBeforeImage.from_document(document)


def test_replace_noop_after_success_and_rejects_stale_plan_or_confirmation():
    approved = user('approved')
    _, snapshot, snapshots = capture((approved,))
    registry = MemoryRegistry((approved,), version='v1')
    promoted, audit, before = MemoryPromoted((approved,)), MemoryAudit(), MemoryBeforeImages()
    target = replacement_service(registry, promoted, snapshots, audit, before)
    validation = target.validate_replace(snapshot.snapshot_id)
    assert validation.plan.unchanged_ids == (approved.user_id,)
    assert not validation.plan.registry_write_required
    with pytest.raises(UsersRecoveryConflictError, match='confirmation'):
        execute_replace(target, validation, confirmed=False)
    with pytest.raises(UsersRecoveryConflictError, match='revocation'):
        execute_replace(target, validation, revocations=False)
    assert not audit.events and not before.images
    promoted.versions[approved.user_id] = 'other-version'
    with pytest.raises(UsersRecoveryConflictError, match='changed'):
        execute_replace(target, validation)
    assert not audit.events and not before.images
    after = execute_replace(target, target.validate_replace(snapshot.snapshot_id))
    assert not after.recovery.differences
    assert registry.replaces == 0 and promoted.creates == 0 and promoted.deletes == 0


def test_replace_partial_delete_failure_can_retry_from_fresh_validation():
    approved = user('approved')
    _, snapshot, snapshots = capture((approved,))
    extra_one, extra_two = user('extra-1'), user('extra-2')
    registry = MemoryRegistry((extra_one, extra_two), version='v1')
    promoted = MemoryPromoted((extra_one, extra_two))
    promoted.fail_delete_after = 1
    audit, before = MemoryAudit(), MemoryBeforeImages()
    target = replacement_service(registry, promoted, snapshots, audit, before)
    with pytest.raises(RuntimeError, match='delete outage'):
        execute_replace(target, target.validate_replace(snapshot.snapshot_id))
    assert ('replace-1', 'failed') in audit.events
    assert len(audit.events[('replace-1', 'failed')].deleted_user_ids) == 1
    assert len(before.images) == 1
    assert registry.snapshot.users == (approved,)
    promoted.fail_delete_after = None
    new_validation = target.validate_replace(snapshot.snapshot_id)
    assert new_validation.can_replace
    result = execute_replace(target, new_validation, operation_id='replace-2')
    assert not result.recovery.differences
    assert set(promoted.users) == {approved.user_id}
    assert registry.replaces == 1
    assert set(before.images) == {'replace-1', 'replace-2'}


def test_replace_needs_valid_profiles_and_immutable_before_image():
    selected = user('approved', profile_key=CUSTOM)
    _, snapshot, snapshots = capture((selected,))
    registry = MemoryRegistry()
    promoted, audit, before = MemoryPromoted(), MemoryAudit(), MemoryBeforeImages()
    target = replacement_service(registry, promoted, snapshots, audit, before, catalog=profiles(False))
    validation = target.validate_replace(snapshot.snapshot_id)
    assert not validation.can_replace
    with pytest.raises(UsersRecoveryConflictError, match='compatible'):
        execute_replace(target, validation)
    assert not audit.events and registry.replaces == 0
    target = replacement_service(registry, promoted, snapshots, audit, before)
    before.available = False
    with pytest.raises(RuntimeError, match='Before-image'):
        execute_replace(target, target.validate_replace(snapshot.snapshot_id))
    assert registry.replaces == 0 and not audit.events


def test_replace_rejects_registry_race_after_before_image_and_audits_failure():
    approved = user('approved')
    _, snapshot, snapshots = capture((approved,))
    registry, promoted, audit = MemoryRegistry(), MemoryPromoted(), MemoryAudit()

    class RacingBeforeImages(MemoryBeforeImages):
        def save(self, image):
            super().save(image)
            registry.snapshot = replace(registry.snapshot, version='externally-modified')

    before = RacingBeforeImages()
    target = replacement_service(registry, promoted, snapshots, audit, before)
    with pytest.raises(UsersRegistryConflictError, match='concurrently'):
        execute_replace(target, target.validate_replace(snapshot.snapshot_id))
    assert registry.replaces == 0
    assert promoted.list_users() == ()
    assert ('replace-1', 'failed') in audit.events
    assert 'replace-1' in before.images
