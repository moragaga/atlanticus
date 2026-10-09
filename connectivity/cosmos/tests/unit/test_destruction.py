from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosContainerDeletion,
    CosmosContainerNotFoundError,
    CosmosPreconditionFailedError,
    CosmosProvisioningError,
    CosmosSettings,
)


class HttpError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


class FakeDatabase:
    def __init__(self):
        self.events = []
        self.failure = None

    def delete_container(self, *args, **kwargs):
        self.events.append((args, kwargs))
        if self.failure:
            raise HttpError(self.failure)


class FakeCosmos(CosmosClient):
    def __init__(self, database):
        self.settings = CosmosSettings(
            endpoint='https://localhost:8081', key='private', database_name='database'
        )
        self.db = database
        self._containers = {'target': object()}

    def _get_database(self):
        return self.db

    def _get_sdk(self):
        return SimpleNamespace(MatchConditions=SimpleNamespace(IfNotModified='if-not-modified'))

    def _raise_sdk_error(self, error, *, not_found_error, not_found_message, operation_message):
        if error.status_code == 404:
            raise not_found_error(not_found_message)
        if error.status_code == 412:
            raise CosmosPreconditionFailedError('Cosmos ETag precondition failed')
        raise RuntimeError(operation_message)


def test_deletion_sends_conditional_etag_and_clears_cache():
    db = FakeDatabase()
    client = FakeCosmos(db)
    CosmosContainerDeletion(client=client).delete_container(
        container_name='target', expected_etag='etag-1'
    )
    assert db.events == [(('target',), {'etag': 'etag-1', 'match_condition': 'if-not-modified'})]
    assert 'target' not in client._containers


@pytest.mark.parametrize(
    'code,error',
    [(404, CosmosContainerNotFoundError), (412, CosmosPreconditionFailedError)],
)
def test_failed_deletion_keeps_cache_and_propagates_typed_error(code, error):
    db = FakeDatabase()
    db.failure = code
    client = FakeCosmos(db)
    with pytest.raises(error):
        CosmosContainerDeletion(client=client).delete_container(
            container_name='target', expected_etag='etag-1'
        )
    assert 'target' in client._containers


@pytest.mark.parametrize('etag', ['', '*', None, '\n'])
def test_deletion_rejects_invalid_etag_before_io(etag):
    db = FakeDatabase()
    with pytest.raises(CosmosProvisioningError):
        CosmosContainerDeletion(client=FakeCosmos(db)).delete_container(
            container_name='target', expected_etag=etag
        )
    assert not db.events
