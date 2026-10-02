from contextlib import contextmanager

from ada.kpis.materialization import KPI_REGISTRY_ITEM_ID
from ada.processes.kpi_materialization.errors import (
    KpiMaterializationAcquisitionError,
    KpiMaterializationRegistryPending,
)


def projection(*, revision: str = 'registry-r1') -> dict[str, object]:
    return {
        'id': KPI_REGISTRY_ITEM_ID,
        'partition_key': 'kpis',
        'document_type': 'ada_kpi_registry_projection_record',
        'schema_version': 1,
        'source_key': 'kpis',
        'source_release_id': revision,
        'source_published_at_utc': '2026-10-02T12:00:00+00:00',
        'projected_at_utc': '2026-10-02T12:00:01+00:00',
        'dependencies': [
            {
                'source_key': 'tool',
                'source_release_id': 'tool-r1',
                'source_published_at_utc': '2026-10-02T11:59:00+00:00',
                'dependencies': [],
            }
        ],
        'payload': {
            'bindings': [
                {
                    'kpi_key': 'crusher.rate',
                    'destination_keys': ['global_indicators'],
                    'latest_enabled': True,
                    'series_enabled': True,
                    'series_hours': 8,
                }
            ]
        },
    }


class Reader:
    def __init__(self, document=None, *, error: Exception | None = None):
        self.document = projection() if document is None else document
        self.error = error

    def read(self):
        if self.error is not None:
            raise self.error
        return self.document


class Context:
    def __init__(self):
        self.work = 0
        self.facts = {}
        self.fences = 0
        self.next_delay = None

    def raise_if_cancelled(self):
        return None

    def assert_lease_current(self):
        return None

    @contextmanager
    def fenced_mutation(self):
        self.fences += 1
        yield

    def mark_iteration_work(self):
        self.work += 1

    def set_iteration_fact(self, key, value):
        self.facts[key] = value

    def set_next_iteration_delay(self, seconds):
        self.next_delay = seconds


def acquisition_error() -> KpiMaterializationAcquisitionError:
    return KpiMaterializationAcquisitionError('unavailable')


def pending_error() -> KpiMaterializationRegistryPending:
    return KpiMaterializationRegistryPending('not ready')
