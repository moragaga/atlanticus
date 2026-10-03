from datetime import UTC, datetime

import pytest

from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.definition.models import (
    KpiDefinition as ConfigurationKpiDefinition,
    KpiDefinitionConfiguration,
)
from ada.web.inspection.core import KpiDefinitionProvider
from ada.web.inspection.providers.kpi_definition import KpiDefinitionProjectionProvider
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId

_SOURCE_KEY = SourceKey('kpi-definitions')


class ProjectionStoreStub:
    def __init__(self, projection: ProjectionRecord[KpiDefinitionCatalog] | None) -> None:
        self.projection = projection
        self.requested_keys: list[SourceKey] = []
        self.replace_calls = 0

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[KpiDefinitionCatalog] | None:
        self.requested_keys.append(source_key)
        return self.projection

    def replace_active(
        self,
        projection: ProjectionRecord[KpiDefinitionCatalog],
    ) -> ProjectionRecord[KpiDefinitionCatalog]:
        self.replace_calls += 1
        self.projection = projection
        return projection


def _projection(*definitions: ConfigurationKpiDefinition) -> ProjectionRecord[KpiDefinitionCatalog]:
    projected_at = datetime(2026, 8, 27, 18, 0, tzinfo=UTC)
    return ProjectionRecord(
        source_key=_SOURCE_KEY,
        source_release_id=SourceReleaseId('source-revision'),
        source_published_at_utc=projected_at,
        projected_at_utc=projected_at,
        payload=KpiDefinitionCatalog(
            configuration=KpiDefinitionConfiguration(definitions=definitions),
            coverage=(),
        ),
    )


def _provider(store: ProjectionStoreStub) -> KpiDefinitionProjectionProvider:
    return KpiDefinitionProjectionProvider(
        projection_store=store,
        source_key=_SOURCE_KEY,
    )


def test_provider_satisfies_inspection_port_and_maps_projection() -> None:
    store = ProjectionStoreStub(
        _projection(
            ConfigurationKpiDefinition(
                kpi_key='transported_total',
                fields={'title': 'Transportado', 'notes': None},
            ),
            ConfigurationKpiDefinition(kpi_key='recovery', fields={'description': 'Recuperación'}),
        )
    )
    provider = _provider(store)

    snapshot = provider.load_snapshot()

    assert isinstance(provider, KpiDefinitionProvider)
    assert store.requested_keys == [_SOURCE_KEY]
    assert tuple(definition.kpi_key for definition in snapshot.definitions) == (
        'transported_total',
        'recovery',
    )
    assert dict(snapshot.definitions[0].fields) == {'title': 'Transportado', 'notes': None}
    assert dict(snapshot.definitions[1].fields) == {'description': 'Recuperación'}


def test_provider_maps_missing_projection_to_empty_snapshot() -> None:
    store = ProjectionStoreStub(None)
    provider = _provider(store)

    snapshot = provider.load_snapshot()

    assert snapshot.definitions == ()
    assert store.requested_keys == [_SOURCE_KEY]


def test_provider_preserves_empty_authoring_stub_without_synthetic_fields() -> None:
    store = ProjectionStoreStub(
        _projection(ConfigurationKpiDefinition(kpi_key='transported_total', fields={}))
    )

    snapshot = _provider(store).load_snapshot()

    assert len(snapshot.definitions) == 1
    assert snapshot.definitions[0].kpi_key == 'transported_total'
    assert dict(snapshot.definitions[0].fields) == {}


def test_provider_reads_projection_only_and_never_writes() -> None:
    store = ProjectionStoreStub(_projection())
    provider = _provider(store)

    provider.load_snapshot()
    provider.load_snapshot()

    assert store.requested_keys == [_SOURCE_KEY, _SOURCE_KEY]
    assert store.replace_calls == 0


def test_provider_reflects_projection_store_snapshot_on_next_lifecycle_load() -> None:
    store = ProjectionStoreStub(
        _projection(
            ConfigurationKpiDefinition(kpi_key='transported_total', fields={'title': 'Old'})
        )
    )
    provider = _provider(store)

    first = provider.load_snapshot()
    store.projection = _projection(
        ConfigurationKpiDefinition(kpi_key='transported_total', fields={'title': 'New'})
    )
    second = provider.load_snapshot()

    assert first.definitions[0].fields['title'] == 'Old'
    assert second.definitions[0].fields['title'] == 'New'


def test_provider_propagates_projection_store_failure_without_fallback_io() -> None:
    class FailingProjectionStore(ProjectionStoreStub):
        def get_active(
            self,
            source_key: SourceKey,
        ) -> ProjectionRecord[KpiDefinitionCatalog] | None:
            raise RuntimeError('Projection unavailable')

    provider = _provider(FailingProjectionStore(None))

    with pytest.raises(RuntimeError, match='Projection unavailable'):
        provider.load_snapshot()
