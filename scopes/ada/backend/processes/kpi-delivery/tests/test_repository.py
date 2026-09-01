from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.kpis.delivery import KpiDeliveryStatus, KpiLatestValue, project_kpi_latest
from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError
from ada.processes.kpi_delivery.models import KpiLatestPublicationStatus
from ada.processes.kpi_delivery.repository import KpiLatestSnapshotRepository
from atlanticus.connectivity.cosmos import CosmosConflictError, CosmosPreconditionFailedError
from tests.support import configuration


class CosmosStub:
    def __init__(self) -> None:
        self.current = None
        self.find_calls = 0
        self.create_calls = 0
        self.patch_calls = 0
        self.patch_error = None
        self.create_error = None
        self.patch_arguments = None
        self.find_sequence = []

    def find_item(self, **_kwargs):
        self.find_calls += 1
        if self.find_sequence:
            return self.find_sequence.pop(0)
        return self.current

    def create_item(self, **kwargs):
        self.create_calls += 1
        if self.create_error is not None:
            raise self.create_error
        self.current = {**kwargs['item'], '_etag': 'etag-created'}
        return kwargs['item']

    def patch_item(self, **kwargs):
        self.patch_calls += 1
        self.patch_arguments = kwargs
        if self.patch_error is not None:
            raise self.patch_error
        operations = kwargs['operations']
        document = dict(self.current)
        for operation in operations:
            document[operation.path.removeprefix('/')] = operation.value
        document['_etag'] = 'etag-patched'
        self.current = document
        return document


def _snapshot(value=42.5):
    return project_kpi_latest(
        configuration=configuration(),
        values={
            'produccion_total': KpiLatestValue(
                status=KpiDeliveryStatus.OK, value_kind='value', value=value
            )
        },
        watermark_utc=datetime(2026, 9, 1, 5, 0, tzinfo=UTC),
        published_at_utc=datetime(2026, 9, 1, 5, 0, 1, tzinfo=UTC),
    )


def test_repository_creates_first_snapshot() -> None:
    cosmos = CosmosStub()
    repository = KpiLatestSnapshotRepository(client=cosmos, container_name='latest')

    publication = repository.publish(_snapshot())

    assert publication.status is KpiLatestPublicationStatus.PUBLISHED
    assert cosmos.create_calls == 1
    assert cosmos.patch_calls == 0


def test_repository_skips_same_revision_without_write() -> None:
    cosmos = CosmosStub()
    snapshot = _snapshot()
    cosmos.current = {**snapshot.to_payload(), '_etag': 'etag-1'}
    repository = KpiLatestSnapshotRepository(client=cosmos, container_name='latest')

    publication = repository.publish(snapshot)

    assert publication.status is KpiLatestPublicationStatus.UNCHANGED
    assert cosmos.create_calls == 0
    assert cosmos.patch_calls == 0


def test_repository_updates_with_etag_fence() -> None:
    cosmos = CosmosStub()
    old = _snapshot(41.0)
    new = _snapshot(42.0)
    cosmos.current = {**old.to_payload(), '_etag': 'etag-1'}
    repository = KpiLatestSnapshotRepository(client=cosmos, container_name='latest')

    publication = repository.publish(new)

    assert publication.status is KpiLatestPublicationStatus.PUBLISHED
    assert cosmos.patch_calls == 1
    assert cosmos.patch_arguments['if_match_etag'] == 'etag-1'


def test_repository_accepts_same_revision_after_create_race() -> None:
    cosmos = CosmosStub()
    snapshot = _snapshot()
    cosmos.create_error = CosmosConflictError('conflict')
    cosmos.find_sequence = [None, {**snapshot.to_payload(), '_etag': 'etag-other'}]
    repository = KpiLatestSnapshotRepository(client=cosmos, container_name='latest')

    publication = repository.publish(snapshot)

    assert publication.status is KpiLatestPublicationStatus.UNCHANGED


def test_repository_rejects_different_revision_after_etag_race() -> None:
    cosmos = CosmosStub()
    old = _snapshot(41.0)
    desired = _snapshot(42.0)
    winner = _snapshot(43.0)
    cosmos.find_sequence = [
        {**old.to_payload(), '_etag': 'etag-old'},
        {**winner.to_payload(), '_etag': 'etag-winner'},
    ]
    cosmos.patch_error = CosmosPreconditionFailedError('stale')
    repository = KpiLatestSnapshotRepository(client=cosmos, container_name='latest')

    with pytest.raises(KpiDeliveryRepositoryError, match='changed concurrently'):
        repository.publish(desired)
