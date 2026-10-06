from datetime import UTC, datetime

from flask import Flask

from ada.web.application.generic.inspection import create_kpi_inspection_modules
from ada.web.inspection.surface import ADA_KPI_INSPECTION_SURFACE_ASSET_LAYER
from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.definition.models import KpiDefinition, KpiDefinitionConfiguration
from atlanticus.web.projection.errors import ProjectionStoreError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey, SourceReleaseId

_SOURCE_KEY = SourceKey('kpi-definitions')
_NOW = datetime(2026, 10, 6, 23, tzinfo=UTC)


class ProjectionStoreStub(ProjectionStore[KpiDefinitionCatalog]):
    def __init__(self, projection: ProjectionRecord[KpiDefinitionCatalog] | None = None):
        self.projection = projection
        self.error: Exception | None = None

    def get_active(self, source_key: SourceKey):
        if self.error is not None:
            raise self.error
        if source_key != _SOURCE_KEY:
            return None
        return self.projection

    def replace_active(self, projection: ProjectionRecord[KpiDefinitionCatalog]):
        self.projection = projection
        return projection


def _projection() -> ProjectionRecord[KpiDefinitionCatalog]:
    return ProjectionRecord(
        source_key=_SOURCE_KEY,
        source_release_id=SourceReleaseId('definitions-r1'),
        source_published_at_utc=_NOW,
        projected_at_utc=_NOW,
        payload=KpiDefinitionCatalog(
            configuration=KpiDefinitionConfiguration(
                definitions=(
                    KpiDefinition(
                        kpi_key='shared.turno.actual',
                        fields={'detail': 'Indicador compartido Mine y Plant.'},
                    ),
                )
            ),
            coverage=(),
        ),
    )


def test_inspection_modules_share_projected_kpi_identity_with_surface_trigger_contract() -> None:
    modules = create_kpi_inspection_modules(ProjectionStoreStub(_projection()))

    assert tuple(module.name for module in modules) == (
        'kpi-inspection-api',
        'kpi-inspection-surface',
    )
    assert modules[1].asset_layers == (ADA_KPI_INSPECTION_SURFACE_ASSET_LAYER,)
    assert 'id="ada-kpi-inspection-surface"' in modules[1].index.body_end_fragments[0]

    server = Flask(__name__)
    modules[0].register_routes(server, ServiceRegistry())
    response = server.test_client().get('/api/inspection/kpis/shared.turno.actual')

    assert response.status_code == 200
    assert response.get_json() == {
        'kpi_key': 'shared.turno.actual',
        'available': True,
        'definition': {'detail': 'Indicador compartido Mine y Plant.'},
    }


def test_unavailable_definition_projection_degrades_inspection_without_failing_composition() -> (
    None
):
    store = ProjectionStoreStub()
    store.error = ProjectionStoreError('unavailable')

    modules = create_kpi_inspection_modules(
        store,
        unavailable_errors=(ProjectionStoreError,),
    )
    server = Flask(__name__)
    modules[0].register_routes(server, ServiceRegistry())
    response = server.test_client().get('/api/inspection/kpis/shared.turno.actual')

    assert response.status_code == 200
    assert response.get_json() == {
        'kpi_key': 'shared.turno.actual',
        'available': False,
        'definition': None,
    }
