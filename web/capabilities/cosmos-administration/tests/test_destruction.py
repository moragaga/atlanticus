from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosContainerNotFoundError,
    CosmosOperationError,
    CosmosPreconditionFailedError,
    CosmosSettings,
)
from atlanticus.web.cosmos_administration import (
    CosmosBackupReport,
    CosmosBackupService,
    CosmosDestructiveOperationError,
    CosmosDestructiveService,
    CosmosLifecycleService,
)
from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    ResolvedStoragePlan,
    ResolvedStorageResource,
)


class HttpError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code


class FakeContainer:
    def __init__(self, name, *, etag='etag-1', exists=True, path='/tenant'):
        self.name = name
        self.etag = etag
        self.exists = exists
        self.path = path

    def read(self):
        if not self.exists:
            raise HttpError(404)
        return {
            'id': self.name,
            'partitionKey': {'paths': [self.path]},
            'defaultTtl': None,
            '_etag': self.etag,
        }


class FakeDatabase:
    def __init__(self):
        self.container = FakeContainer('runtime-users')
        self.deletes = []
        self.creates = []

    def read(self):
        return {'id': 'database'}

    def get_container_client(self, name):
        assert name == 'runtime-users'
        return self.container

    def delete_container(self, name, *, etag, match_condition):
        self.deletes.append((name, etag, match_condition))
        if not self.container.exists:
            raise HttpError(404)
        if etag != self.container.etag:
            raise HttpError(412)
        self.container.exists = False

    def create_container(self, *, id, partition_key, default_ttl):
        self.creates.append((id, partition_key.path, default_ttl))
        if self.container.exists:
            raise HttpError(409)
        self.container = FakeContainer(id, etag='etag-2', path=partition_key.path)
        return self.container


class FakeCosmos(CosmosClient):
    def __init__(self):
        self.settings = CosmosSettings(
            endpoint='https://localhost:8081', key='private', database_name='database'
        )
        self.database = FakeDatabase()
        self._containers = {}

    def health_check(self):
        return True

    def _get_database(self):
        return self.database

    def _get_container(self, name):
        return self.database.get_container_client(name)

    def _get_sdk(self):
        return SimpleNamespace(
            PartitionKey=lambda *, path: SimpleNamespace(path=path),
            MatchConditions=SimpleNamespace(IfNotModified='if-not-modified'),
        )

    def _raise_sdk_error(self, error, *, not_found_error, not_found_message, operation_message):
        if getattr(error, 'status_code', None) == 404:
            raise not_found_error(not_found_message)
        if getattr(error, 'status_code', None) == 412:
            raise CosmosPreconditionFailedError('Cosmos ETag precondition failed')
        raise CosmosOperationError(operation_message)


class FakeBackups(CosmosBackupService):
    def __init__(
        self, *, connection_ref='main', database_name='database', container_name='runtime-users'
    ):
        self.connection_ref = connection_ref
        self.database_name = database_name
        self.container_name = container_name
        self.calls = []
        self.failed = False

    def verify_backup(self, *, destination_ref, backup_id):
        self.calls.append((destination_ref, backup_id))
        if self.failed:
            raise RuntimeError('Backup verification failed')
        return CosmosBackupReport(
            backup_id=backup_id,
            connection_ref=self.connection_ref,
            database_name=self.database_name,
            container_name=self.container_name,
            destination_ref=destination_ref,
            manifest_blob_name='backups/manifest.json',
            document_count=5,
            chunk_count=1,
            verified=True,
            point_in_time_consistent=False,
        )


class FakeAudit:
    def __init__(self):
        self.events = []
        self.fail_stage = None

    def record(self, *, action_id, stage, payload):
        if stage == self.fail_stage:
            raise RuntimeError('Audit unavailable')
        self.events.append((action_id, stage, dict(payload)))


def make_service(*, root='admin'):
    client = FakeCosmos()
    resource = ResolvedStorageResource(
        logical_id='runtime',
        owner='sample',
        provider='cosmos',
        connection_ref='main',
        physical_name='runtime-users',
        topology=CosmosContainerTopology(partition_key_path='/tenant'),
    )
    lifecycle = CosmosLifecycleService(
        connections={'main': client},
        plan=ResolvedStoragePlan(resources=(resource,)),
    )
    backups = FakeBackups()
    audit = FakeAudit()
    service = CosmosDestructiveService(
        lifecycle=lifecycle,
        backups=backups,
        audit=audit,
        authenticated_root=lambda: root,
    )
    return service, client, backups, audit


def args(service):
    preview = service.inspect(logical_id='runtime')
    return {
        'logical_id': 'runtime',
        'expected_etag': preview.physical.etag,
        'confirmation_target': preview.confirmation_target,
        'destination_ref': 'durable',
        'backup_id': 'b' * 32,
        'acknowledge_data_loss': True,
    }


def test_delete_uses_conditional_etag_and_verified_audit():
    service, client, backups, audit = make_service()
    result = service.delete_container(**args(service))
    assert result.status == 'DELETED'
    assert result.point_in_time_consistent is False
    assert client.database.deletes == [('runtime-users', 'etag-1', 'if-not-modified')]
    assert backups.calls == [('durable', 'b' * 32)]
    assert [event[1] for event in audit.events] == ['intent', 'completed']
    assert audit.events[0][0] == audit.events[1][0]


def test_recreate_reuses_approved_spec_and_validates():
    service, client, _, audit = make_service()
    result = service.recreate_container(**args(service))
    assert result.status == 'RECREATED'
    assert client.database.creates == [('runtime-users', '/tenant', None)]
    assert client.database.container.exists
    assert client.database.container.etag == 'etag-2'
    assert [event[1] for event in audit.events] == ['intent', 'completed']


def test_missing_root_prevents_destructive_operation():
    service, client, backups, audit = make_service(root=None)
    with pytest.raises(CosmosDestructiveOperationError, match='ROOT'):
        service.delete_container(**args(service))
    assert not backups.calls and not audit.events and not client.database.deletes


@pytest.mark.parametrize(
    'field,value',
    [
        ('acknowledge_data_loss', False),
        ('confirmation_target', 'wrong'),
        ('expected_etag', 'wrong'),
    ],
)
def test_missing_acknowledgement_or_stale_preview_blocks_before_backup(field, value):
    service, client, backups, audit = make_service()
    values = args(service)
    values[field] = value
    error_type = (
        CosmosPreconditionFailedError
        if field == 'expected_etag'
        else CosmosDestructiveOperationError
    )
    with pytest.raises(error_type):
        service.delete_container(**values)
    assert not client.database.deletes and not backups.calls and not audit.events


def test_backup_must_match_exact_cosmos_binding():
    service, client, backups, audit = make_service()
    backups.database_name = 'other'
    with pytest.raises(CosmosDestructiveOperationError, match='does not match'):
        service.delete_container(**args(service))
    assert not audit.events and not client.database.deletes


def test_backup_failure_prevents_deletion():
    service, client, backups, audit = make_service()
    backups.failed = True
    with pytest.raises(RuntimeError, match='Backup verification'):
        service.delete_container(**args(service))
    assert not audit.events and not client.database.deletes


def test_audit_intent_must_succeed_before_deletion():
    service, client, _, audit = make_service()
    audit.fail_stage = 'intent'
    with pytest.raises(RuntimeError, match='Audit unavailable'):
        service.delete_container(**args(service))
    assert not client.database.deletes


def test_concurrent_change_during_delete_records_failed_event_and_never_recreates():
    service, client, _, audit = make_service()
    values = args(service)

    def fail_on_delete(*args, **kwargs):
        raise HttpError(412)

    client.database.delete_container = fail_on_delete
    with pytest.raises(CosmosPreconditionFailedError):
        service.recreate_container(**values)
    assert client.database.creates == []
    assert [event[1] for event in audit.events] == ['intent', 'failed']
    assert audit.events[-1][2]['physical_deletion_completed'] is False


def test_unapproved_resource_is_not_destructible():
    service, _, _, _ = make_service()
    with pytest.raises(ValueError, match='not approved'):
        service.inspect(logical_id='third-party')


def test_missing_resource_refuses_preview():
    service, client, _, _ = make_service()
    client.database.container.exists = False
    with pytest.raises(CosmosContainerNotFoundError):
        service.inspect(logical_id='runtime')


def test_recreation_failure_is_audited_after_deletion():
    service, client, _, audit = make_service()
    values = args(service)

    def fail_create(**kwargs):
        raise HttpError(500)

    client.database.create_container = fail_create
    with pytest.raises(CosmosOperationError):
        service.recreate_container(**values)
    assert not client.database.container.exists
    assert [event[1] for event in audit.events] == ['intent', 'failed']
    assert audit.events[-1][2]['physical_deletion_completed'] is True


def test_audit_completion_failure_does_not_claim_success():
    service, client, _, audit = make_service()
    values = args(service)
    audit.fail_stage = 'completed'
    with pytest.raises(RuntimeError, match='Audit unavailable'):
        service.delete_container(**values)
    assert not client.database.container.exists
    assert [event[1] for event in audit.events] == ['intent']


def test_recreate_replaces_incompatible_partition_only_after_explicit_confirmation():
    service, client, _, audit = make_service()
    client.database.container.path = '/unexpected'
    preview = service.inspect(logical_id='runtime')
    assert preview.physical.partition_key_paths == ('/unexpected',)
    result = service.recreate_container(**args(service))
    assert result.status == 'RECREATED'
    assert client.database.container.path == '/tenant'
    assert [event[1] for event in audit.events] == ['intent', 'completed']


def test_missing_etag_blocks_destruction_during_inspection():
    service, client, _, audit = make_service()
    client.database.container.etag = None
    with pytest.raises(CosmosDestructiveOperationError, match='ETag'):
        service.inspect(logical_id='runtime')
    assert not audit.events and not client.database.deletes
