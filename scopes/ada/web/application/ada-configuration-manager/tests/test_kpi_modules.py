from dataclasses import replace

from ada.web.application.configuration_manager import build_configuration_manager_surface
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey

from .test_composition import ProjectionStub, SourceStub, dependencies


class EmptyProjectionStore(ProjectionStore[object]):
    def get_active(self, source_key: SourceKey):
        return None

    def replace_active(self, projection):
        return projection


class DestinationProviderStub:
    def load(self):
        return None


def test_kpi_and_definition_are_optional_direct_generic_modules() -> None:
    kpi_store = EmptyProjectionStore()
    injected = replace(
        dependencies(),
        kpi_registry_source=SourceStub('kpis'),
        kpi_registry_projection=ProjectionStub(),
        kpi_registry_destinations=DestinationProviderStub(),
        kpi_registry_projection_store=kpi_store,
        kpi_definitions_source=SourceStub('kpi-definitions'),
        kpi_definitions_projection=ProjectionStub(),
    )

    definition = build_configuration_manager_surface(injected)

    assert tuple(module.key for module in definition.modules) == (
        'profiles',
        'access',
        'navigation',
        'tools',
        'kpis',
        'kpi-definitions',
    )
    kpis = definition.modules[4]
    definitions = definition.modules[5]
    assert kpis.source_key == SourceKey('kpis')
    assert definitions.source_key == SourceKey('kpi-definitions')
    assert kpis.source_service.endswith('.kpis.source')
    assert definitions.source_service.endswith('.kpi-definitions.source')
