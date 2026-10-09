from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from atlanticus.connectivity.cosmos import CosmosClient, CosmosPage, CosmosSettings
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.cosmos_administration import (
    CosmosBackupConfigurationError,
    CosmosBackupDestination,
    CosmosBackupError,
    CosmosBackupIntegrityError,
    CosmosBackupService,
)


class FakeContainer:
    def __init__(self, name='records', path='/tenant', ttl=None):
        self.name = name
        self.path = path
        self.ttl = ttl

    def read(self):
        return {
            'id': self.name,
            'partitionKey': {'paths': [self.path]},
            'defaultTtl': self.ttl,
        }


class FakeCosmos(CosmosClient):
    def __init__(self, pages):
        self.settings = CosmosSettings(
            endpoint='https://localhost:8081', key='private-key', database_name='database'
        )
        self.pages = list(pages)
        self.container = FakeContainer()
        self.health_checks = 0
        self.queries = []

    def health_check(self):
        self.health_checks += 1
        return True

    def _get_container(self, name):
        assert name == 'records'
        return self.container

    def query_page(self, **kwargs):
        self.queries.append(kwargs)
        return self.pages.pop(0)


class FakeStorage(StorageClient):
    def __init__(self):
        self.blobs = {}
        self.corrupt_on_download = False
        self.uploaded = []

    def upload(self, *, container_name, blob_name, data, overwrite, content_type):
        assert container_name == 'backups'
        assert overwrite is False
        assert blob_name not in self.blobs
        self.blobs[blob_name] = bytes(data)
        self.uploaded.append((blob_name, content_type))

    def download_to(self, *, container_name, blob_name, target):
        assert container_name == 'backups'
        data = self.blobs[blob_name]
        if self.corrupt_on_download:
            data = data + b'x'
        return target.write(data)

    def get_properties(self, *, container_name, blob_name):
        return SimpleNamespace(size=len(self.blobs[blob_name]))

    def download(self, *, container_name, blob_name):
        return self.blobs[blob_name]


def sample(pages):
    source = FakeCosmos(pages)
    storage = FakeStorage()
    service = CosmosBackupService(
        cosmos_connections={'primary': source},
        storage_connections={'archive': storage},
        destinations={
            'durable': CosmosBackupDestination(
                storage_ref='archive', container_name='backups', blob_prefix='cosmos/backups'
            )
        },
    )
    return service, source, storage


def create(service, **overrides):
    arguments = {
        'connection_ref': 'primary',
        'container_name': 'records',
        'destination_ref': 'durable',
        'operator_id': 'administrator',
    }
    return service.create_backup(**(arguments | overrides))


def test_backup_writes_verified_chunks_and_complete_manifest():
    service, source, storage = sample(
        [
            CosmosPage(items=({'id': 'a', 'tenant': 'x'},), continuation_token='next'),
            CosmosPage(items=({'id': 'b', 'tenant': 'y'},), continuation_token=None),
        ]
    )
    result = create(service)
    assert result.verified is True
    assert result.point_in_time_consistent is False
    assert result.document_count == 2
    assert result.chunk_count == 2
    assert source.health_checks == 2
    assert len(source.queries) == 2
    assert source.queries[0]['continuation_token'] is None
    assert source.queries[1]['continuation_token'] == 'next'
    assert all(query['cross_partition'] is True for query in source.queries)
    assert all(query['include_metadata'] is False for query in source.queries)
    manifest = json.loads(storage.blobs[result.manifest_blob_name])
    assert manifest['status'] == 'COMPLETE'
    assert manifest['source']['partition_key_paths'] == ['/tenant']
    assert manifest['point_in_time_consistent'] is False
    assert manifest['document_count'] == 2
    assert 'private-key' not in str(manifest)
    assert service.verify_backup(destination_ref='durable', backup_id=result.backup_id) == result


def test_empty_container_publishes_manifest_without_chunks():
    service, _, storage = sample([CosmosPage(items=(), continuation_token=None)])
    result = create(service)
    assert result.document_count == 0
    assert result.chunk_count == 0
    assert len(storage.blobs) == 1
    assert service.verify_backup(destination_ref='durable', backup_id=result.backup_id) == result


def test_empty_intermediate_page_continues():
    service, source, _ = sample(
        [
            CosmosPage(items=(), continuation_token='a'),
            CosmosPage(items=({'id': 'doc'},), continuation_token=None),
        ]
    )
    result = create(service)
    assert result.document_count == 1
    assert len(source.queries) == 2


def test_integrity_mismatch_does_not_publish_complete_manifest():
    service, _, storage = sample([CosmosPage(items=({'id': 'a'},), continuation_token=None)])
    storage.corrupt_on_download = True
    with pytest.raises(CosmosBackupIntegrityError):
        create(service)
    assert not any(name.endswith('manifest.json') for name in storage.blobs)


def test_verify_detects_chunk_modification_after_backup():
    service, _, storage = sample([CosmosPage(items=({'id': 'a'},), continuation_token=None)])
    result = create(service)
    chunk = next(name for name in storage.blobs if name.endswith('.ndjson'))
    storage.blobs[chunk] = storage.blobs[chunk] + b'garbage\n'
    with pytest.raises(CosmosBackupIntegrityError):
        service.verify_backup(destination_ref='durable', backup_id=result.backup_id)


def test_changed_partition_key_aborts_publication():
    service, source, storage = sample([CosmosPage(items=({'id': 'a'},), continuation_token=None)])
    original = source.container.read
    calls = 0

    def change():
        nonlocal calls
        calls += 1
        result = original()
        if calls > 1:
            result['partitionKey']['paths'] = ['/new']
        return result

    source.container.read = change
    with pytest.raises(CosmosBackupError, match='definition changed'):
        create(service)
    assert not any(name.endswith('manifest.json') for name in storage.blobs)


def test_continuation_cycle_fails_closed():
    service, _, storage = sample(
        [CosmosPage(items=(), continuation_token='t'), CosmosPage(items=(), continuation_token='t')]
    )
    with pytest.raises(CosmosBackupError, match='did not advance'):
        create(service)
    assert storage.blobs == {}


def test_max_pages_fails_closed():
    service, _, storage = sample([CosmosPage(items=(), continuation_token='more')])
    with pytest.raises(CosmosBackupError, match='max_pages'):
        create(service, max_pages=1)
    assert storage.blobs == {}


def test_page_size_limit_fails_before_upload():
    service, _, storage = sample(
        [CosmosPage(items=({'id': 'large', 'text': 'x' * 500},), continuation_token=None)]
    )
    with pytest.raises(CosmosBackupError, match='max_page_bytes'):
        create(service, max_page_bytes=20)
    assert storage.blobs == {}


def test_non_serializable_document_fails_before_upload():
    service, _, storage = sample(
        [CosmosPage(items=({'id': 'a', 'bad': object()},), continuation_token=None)]
    )
    with pytest.raises(CosmosBackupError, match='non-JSON'):
        create(service)
    assert storage.blobs == {}


def test_wrong_connection_and_destination_do_not_fall_back():
    service, source, storage = sample([])
    with pytest.raises(CosmosBackupConfigurationError):
        create(service, connection_ref='other')
    with pytest.raises(CosmosBackupConfigurationError):
        create(service, destination_ref='other')
    assert not source.queries
    assert not storage.blobs


@pytest.mark.parametrize('prefix', ['/root', 'foo/../bar', 'foo//bar', 'foo\\bar', 'foo/'])
def test_invalid_destination_prefix_is_rejected(prefix):
    with pytest.raises(CosmosBackupConfigurationError):
        CosmosBackupDestination(storage_ref='archive', container_name='backups', blob_prefix=prefix)


def test_unknown_storage_connection_is_rejected():
    with pytest.raises(CosmosBackupConfigurationError):
        CosmosBackupService(
            cosmos_connections={'primary': FakeCosmos([])},
            storage_connections={'archive': FakeStorage()},
            destinations={
                'durable': CosmosBackupDestination(
                    storage_ref='wrong', container_name='backups', blob_prefix='cosmos/backups'
                )
            },
        )


def test_verify_rejects_untrusted_identifier_before_storage():
    service, _, storage = sample([])
    with pytest.raises(CosmosBackupConfigurationError):
        service.verify_backup(destination_ref='durable', backup_id='../sensitive')
    assert storage.blobs == {}


def test_readback_manifest_contract_rejects_forged_document_count():
    service, _, storage = sample([CosmosPage(items=({'id': 'one'},), continuation_token=None)])
    result = create(service)
    manifest = json.loads(storage.blobs[result.manifest_blob_name])
    manifest['document_count'] = 99
    storage.blobs[result.manifest_blob_name] = json.dumps(manifest).encode()
    with pytest.raises(CosmosBackupIntegrityError, match='count mismatch'):
        service.verify_backup(destination_ref='durable', backup_id=result.backup_id)
