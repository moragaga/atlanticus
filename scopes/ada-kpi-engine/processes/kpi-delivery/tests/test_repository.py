from datetime import UTC, datetime

import pytest

from ada.kpis.delivery import (
    KpiDeliveryStatus,
    KpiLatestValue,
    project_kpi_latest,
)
from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError
from ada.processes.kpi_delivery.models import KpiLatestPublicationStatus
from ada.processes.kpi_delivery.repository import KpiLatestSnapshotRepository
from atlanticus.connectivity.cosmos import (
    CosmosConflictError,
    CosmosContainerSpec,
    CosmosOperationError,
    CosmosPreconditionFailedError,
)

from .support import configuration


class ProvisionerStub:
    def __init__(self):
        self.calls = 0

    def ensure_containers(self, specs):
        self.calls += 1
        return tuple(spec.name for spec in specs)


class CosmosStub:
    def __init__(self):
        self.current = None
        self.find_calls = 0
        self.create_calls = 0
        self.patch_calls = 0
        self.patch_error = None
        self.create_error = None
        self.find_error = None
        self.patch_arguments = None
        self.find_sequence = []

    def find_item(self, **_kwargs):
        self.find_calls += 1
        if self.find_error is not None:
            raise self.find_error
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
        document = dict(self.current)
        for operation in kwargs['operations']:
            document[operation.path.removeprefix('/')] = operation.value
        document['_etag'] = 'etag-patched'
        self.current = document
        return document


def _repository(cosmos):
    spec = CosmosContainerSpec(
        name='latest',
        partition_key_path='/partition_id',
        default_ttl_seconds=None,
    )
    provisioner = ProvisionerStub()
    return (
        KpiLatestSnapshotRepository(
            client=cosmos,
            provisioner=provisioner,
            container_spec=spec,
        ),
        provisioner,
    )


def _snapshot(value=42.5):
    return project_kpi_latest(
        configuration=configuration(),
        values={
            'produccion_total': KpiLatestValue(
                status=KpiDeliveryStatus.OK,
                value_kind='value',
                value=str(value),
                value_type='float',
                parsed_value=str(value).replace('.', ','),
            )
        },
        watermark_utc=datetime(2026, 9, 1, 5, 0, tzinfo=UTC),
        published_at_utc=datetime(2026, 9, 1, 5, 0, 1, tzinfo=UTC),
    )


def test_repository_provisions_lazily_and_only_once():
    cosmos = CosmosStub()
    repository, provisioner = _repository(cosmos)

    repository.publish(_snapshot())
    repository.publish(_snapshot())

    assert provisioner.calls == 1


def test_repository_creates_first_snapshot_and_skips_same_revision():
    cosmos = CosmosStub()
    repository, _ = _repository(cosmos)
    snapshot = _snapshot()

    first = repository.publish(snapshot)
    second = repository.publish(snapshot)

    assert first.status is KpiLatestPublicationStatus.PUBLISHED
    assert second.status is KpiLatestPublicationStatus.UNCHANGED
    assert cosmos.create_calls == 1


def test_repository_updates_with_etag_fence():
    cosmos = CosmosStub()
    old = _snapshot(41.0)
    new = _snapshot(42.0)
    cosmos.current = {**old.to_payload(), '_etag': 'etag-1'}
    repository, _ = _repository(cosmos)

    publication = repository.publish(new)

    assert publication.status is KpiLatestPublicationStatus.PUBLISHED
    assert cosmos.patch_arguments['if_match_etag'] == 'etag-1'


def test_repository_accepts_same_revision_after_create_race():
    cosmos = CosmosStub()
    snapshot = _snapshot()
    cosmos.create_error = CosmosConflictError('conflict')
    cosmos.find_sequence = [None, {**snapshot.to_payload(), '_etag': 'etag-other'}]
    repository, _ = _repository(cosmos)

    assert repository.publish(snapshot).status is KpiLatestPublicationStatus.UNCHANGED


def test_repository_rejects_different_revision_after_etag_race():
    cosmos = CosmosStub()
    old = _snapshot(41.0)
    desired = _snapshot(42.0)
    winner = _snapshot(43.0)
    cosmos.find_sequence = [
        {**old.to_payload(), '_etag': 'etag-old'},
        {**winner.to_payload(), '_etag': 'etag-winner'},
    ]
    cosmos.patch_error = CosmosPreconditionFailedError('stale')
    repository, _ = _repository(cosmos)

    with pytest.raises(KpiDeliveryRepositoryError, match='changed concurrently'):
        repository.publish(desired)


def test_repository_normalizes_cosmos_failure():
    cosmos = CosmosStub()
    cosmos.find_error = CosmosOperationError('unavailable')
    repository, _ = _repository(cosmos)

    with pytest.raises(KpiDeliveryRepositoryError, match='Could not publish'):
        repository.publish(_snapshot())
