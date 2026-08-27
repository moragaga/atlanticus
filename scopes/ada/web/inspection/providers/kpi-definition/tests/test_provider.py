from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_definition import (
    KpiDefinition as ConfigurationKpiDefinition,
    KpiDefinitionConfiguration,
    KpiDefinitionProjection,
)
from ada.web.inspection.core import KpiDefinitionProvider
from ada.web.inspection.providers.kpi_definition import KpiDefinitionProjectionProvider


class ProjectionRepository:
    def __init__(self, projection: KpiDefinitionProjection | None) -> None:
        self.projection = projection
        self.load_calls = 0
        self.save_calls = 0
        self.health_calls = 0

    def load(self) -> KpiDefinitionProjection | None:
        self.load_calls += 1
        return self.projection

    def save(self, projection: KpiDefinitionProjection) -> KpiDefinitionProjection:
        self.save_calls += 1
        self.projection = projection
        return projection

    def health_check(self) -> bool:
        self.health_calls += 1
        return True


def _projection(*definitions: ConfigurationKpiDefinition) -> KpiDefinitionProjection:
    return KpiDefinitionProjection.create(
        configuration=KpiDefinitionConfiguration(definitions=definitions),
        source_revision='source-revision',
        projected_by='projector',
        projected_at_utc=datetime(2026, 8, 27, 18, 0, tzinfo=UTC),
    )


def test_provider_satisfies_inspection_port_and_maps_projection() -> None:
    repository = ProjectionRepository(
        _projection(
            ConfigurationKpiDefinition(
                kpi_key='transported_total',
                fields={'title': 'Transportado', 'notes': None},
            ),
            ConfigurationKpiDefinition(kpi_key='recovery', fields={'description': 'Recuperación'}),
        )
    )
    provider = KpiDefinitionProjectionProvider(repository)

    snapshot = provider.load_snapshot()

    assert isinstance(provider, KpiDefinitionProvider)
    assert repository.load_calls == 1
    assert tuple(definition.kpi_key for definition in snapshot.definitions) == (
        'transported_total',
        'recovery',
    )
    assert dict(snapshot.definitions[0].fields) == {'title': 'Transportado', 'notes': None}
    assert dict(snapshot.definitions[1].fields) == {'description': 'Recuperación'}


def test_provider_maps_missing_projection_to_empty_snapshot() -> None:
    repository = ProjectionRepository(None)
    provider = KpiDefinitionProjectionProvider(repository)

    snapshot = provider.load_snapshot()

    assert snapshot.definitions == ()
    assert repository.load_calls == 1


def test_provider_preserves_empty_authoring_stub_without_synthetic_fields() -> None:
    repository = ProjectionRepository(
        _projection(ConfigurationKpiDefinition(kpi_key='transported_total', fields={}))
    )

    snapshot = KpiDefinitionProjectionProvider(repository).load_snapshot()

    assert len(snapshot.definitions) == 1
    assert snapshot.definitions[0].kpi_key == 'transported_total'
    assert dict(snapshot.definitions[0].fields) == {}


def test_provider_reads_projection_only_and_never_writes_or_health_checks() -> None:
    repository = ProjectionRepository(_projection())
    provider = KpiDefinitionProjectionProvider(repository)

    provider.load_snapshot()
    provider.load_snapshot()

    assert repository.load_calls == 2
    assert repository.save_calls == 0
    assert repository.health_calls == 0


def test_provider_reflects_repository_snapshot_on_next_lifecycle_load() -> None:
    repository = ProjectionRepository(
        _projection(
            ConfigurationKpiDefinition(kpi_key='transported_total', fields={'title': 'Old'})
        )
    )
    provider = KpiDefinitionProjectionProvider(repository)

    first = provider.load_snapshot()
    repository.projection = _projection(
        ConfigurationKpiDefinition(kpi_key='transported_total', fields={'title': 'New'})
    )
    second = provider.load_snapshot()

    assert first.definitions[0].fields['title'] == 'Old'
    assert second.definitions[0].fields['title'] == 'New'


def test_provider_propagates_repository_failure_without_fallback_io() -> None:
    class FailingRepository(ProjectionRepository):
        def load(self) -> KpiDefinitionProjection | None:
            raise RuntimeError('Projection unavailable')

    provider = KpiDefinitionProjectionProvider(FailingRepository(None))

    with pytest.raises(RuntimeError, match='Projection unavailable'):
        provider.load_snapshot()
