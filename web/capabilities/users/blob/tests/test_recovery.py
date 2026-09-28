from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from atlanticus.connectivity.storage import StorageBlobNotFoundError, StorageConflictError
from atlanticus.connectivity.storage.models import StorageBlobProperties
from atlanticus.web.users.blob.recovery import (
    BlobApprovedUsersSnapshotStore,
    BlobUsersRecoveryAuditStore,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import UserRecord
from atlanticus.web.users.recovery import (
    ApprovedUsersSnapshot,
    UsersRecoveryAuditEvent,
    UsersRecoveryConflictError,
)


class FakeBlobClient:
    def __init__(self):
        self.data = {}
        self.sequence = 0

    def upload(
        self,
        *,
        container_name,
        blob_name,
        data,
        overwrite=True,
        metadata=None,
        content_type=None,
    ):
        assert container_name in {'snapshots', 'audit', 'source', 'target'}
        assert content_type in {'application/json', 'application/gzip'}
        key = container_name, blob_name
        if key in self.data and not overwrite:
            raise StorageConflictError
        self.sequence += 1
        self.data[key] = (bytes(data), f'etag-{self.sequence}')

    def upload_if_match(
        self,
        *,
        container_name,
        blob_name,
        data,
        etag,
        metadata=None,
        content_type=None,
    ):
        key = container_name, blob_name
        if key not in self.data or self.data[key][1] != etag:
            raise StorageConflictError
        self.upload(
            container_name=container_name,
            blob_name=blob_name,
            data=data,
            overwrite=True,
            content_type=content_type,
        )

    def download(self, *, container_name, blob_name):
        try:
            return self.data[(container_name, blob_name)][0]
        except KeyError as error:
            raise StorageBlobNotFoundError from error

    def get_properties(self, *, container_name, blob_name):
        try:
            raw, etag = self.data[(container_name, blob_name)]
        except KeyError as error:
            raise StorageBlobNotFoundError from error
        return StorageBlobProperties(name=blob_name, size=len(raw), etag=etag)


def snapshot():
    user = UserRecord(
        user_id=build_user_key(issuer='entra', subject_id='one'),
        issuer='entra',
        subject_id='one',
        display_name='User One',
        email=None,
        enabled=True,
        profile_key='basic',
    )
    return ApprovedUsersSnapshot(
        snapshot_id='snapshot-1',
        application_key='ada-generic',
        identity_realm='tenant-1',
        origin_environment='DEV',
        captured_at_utc=datetime.now(UTC).isoformat(),
        operator_id='operator',
        approval_reference='ticket-1',
        users=(user,),
    )


def test_approved_snapshots_are_immutable_and_validate_loaded_content():
    client = FakeBlobClient()
    store = BlobApprovedUsersSnapshotStore(
        client=client, container_name='snapshots', prefix='ada-generic/users/approved'
    )
    saved = snapshot()
    store.save(saved)
    assert store.load(saved.snapshot_id) == saved
    with pytest.raises(UsersRecoveryConflictError, match='already exists'):
        store.save(saved)
    name = 'ada-generic/users/approved/snapshot-1.json'
    raw, etag = client.data[('snapshots', name)]
    document = json.loads(raw.decode('utf-8'))
    document['users'][0]['profile_key'] = 'root'
    client.data[('snapshots', name)] = (json.dumps(document).encode('utf-8'), etag)
    with pytest.raises(UsersRecoveryConflictError, match='invalid'):
        store.load(saved.snapshot_id)


def test_snapshot_id_cannot_escape_blob_prefix():
    client = FakeBlobClient()
    store = BlobApprovedUsersSnapshotStore(
        client=client, container_name='snapshots', prefix='ada-generic/users/approved'
    )
    with pytest.raises(ValueError, match='invalid format'):
        store.load('../elsewhere')


def test_audit_events_are_immutable_and_separate_from_snapshots():
    client = FakeBlobClient()
    audit = BlobUsersRecoveryAuditStore(
        client=client, container_name='audit', prefix='ada-generic/users/recovery-audit'
    )
    event = UsersRecoveryAuditEvent(
        operation_id='operation-1',
        stage='started',
        snapshot_id='snapshot-1',
        snapshot_digest=snapshot().content_digest,
        target_environment='UAT',
        operator_id='operator',
        approval_reference='ticket-2',
        at_utc=datetime.now(UTC).isoformat(),
    )
    audit.record(event)
    key = ('audit', 'ada-generic/users/recovery-audit/operation-1-started.json')
    assert json.loads(client.data[key][0].decode('utf-8'))['snapshot_id'] == 'snapshot-1'
    with pytest.raises(UsersRecoveryConflictError, match='already exists'):
        audit.record(event)


def test_capture_and_restore_through_real_blob_registry_and_snapshot_adapters():
    from atlanticus.web.profiles.models import ProfileCatalog
    from atlanticus.web.users.blob import BlobUsersRegistryStore
    from atlanticus.web.users.recovery import UsersApprovedRecoveryService
    from atlanticus.web.users.store import UsersAdministrationStore

    class Promoted(UsersAdministrationStore):
        def __init__(self, initial=()):
            self.users = {value.user_id: value for value in initial}

        def get(self, user_id):
            return self.users.get(user_id)

        def list_users(self):
            return tuple(self.users.values())

        def create(self, value):
            if value.user_id in self.users:
                raise RuntimeError('User is already promoted')
            self.users[value.user_id] = value
            return value

        def replace(self, value):
            self.users[value.user_id] = value
            return value

    client = FakeBlobClient()
    approved = snapshot().users[0]
    registered_candidate = UserRecord(
        user_id=build_user_key(issuer='entra', subject_id='guest'),
        issuer='entra',
        subject_id='guest',
        display_name='Pending Guest',
        email=None,
        enabled=False,
        profile_key='guest',
    )
    source_registry = BlobUsersRegistryStore(
        client=client, container_name='source', blob_name='ada-generic/users/users.json.gz'
    )
    source_registry.replace((approved, registered_candidate), expected_version=None)
    target_registry = BlobUsersRegistryStore(
        client=client, container_name='target', blob_name='ada-generic/users/users.json.gz'
    )
    artifacts = BlobApprovedUsersSnapshotStore(
        client=client, container_name='snapshots', prefix='ada-generic/users/approved'
    )
    audit = BlobUsersRecoveryAuditStore(
        client=client, container_name='audit', prefix='ada-generic/users/recovery-audit'
    )

    def make_service(registry, promoted, environment):
        return UsersApprovedRecoveryService(
            registry=registry,
            promoted=promoted,
            profiles=ProfileCatalog,
            snapshots=artifacts,
            audit=audit,
            application_key='ada-generic',
            identity_realm='tenant-1',
            environment=environment,
        )

    origin = make_service(source_registry, Promoted((approved,)), 'DEV')
    preview = origin.preview_capture()
    assert preview.candidate_user_ids == (registered_candidate.user_id,)
    saved = origin.capture(
        preview=preview,
        approved_user_ids=(approved.user_id,),
        operator_id='operator',
        approval_reference='capture-ticket',
        confirmed=True,
    )
    destination = make_service(target_registry, Promoted(), 'UAT')
    validation = destination.validate(saved.snapshot_id)
    assert validation.can_restore
    after = destination.restore(
        validation=validation,
        confirmed_digest=saved.content_digest,
        operator_id='operator',
        approval_reference='restore-ticket',
        operation_id='operation-1',
        confirmed=True,
        maintenance_confirmed=True,
    )
    assert not after.differences
    assert target_registry.load().users == (approved,)
    assert source_registry.load().users == tuple(sorted((registered_candidate, approved), key=lambda u: u.user_id))
    assert ('audit', 'ada-generic/users/recovery-audit/operation-1-started.json') in client.data
    assert ('audit', 'ada-generic/users/recovery-audit/operation-1-completed.json') in client.data


def test_snapshot_load_rejects_physical_change_during_read():
    client = FakeBlobClient()
    store = BlobApprovedUsersSnapshotStore(
        client=client, container_name='snapshots', prefix='ada-generic/users/approved'
    )
    saved = snapshot()
    store.save(saved)

    def changed_download(*, container_name, blob_name):
        raw, _ = client.data[(container_name, blob_name)]
        client.data[(container_name, blob_name)] = (raw, 'changed-etag')
        return raw

    client.download = changed_download
    with pytest.raises(UsersRecoveryConflictError, match='changed during read'):
        store.load(saved.snapshot_id)
