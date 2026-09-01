from datetime import UTC, datetime

from ada.configuration.kpi_configuration import (
    KpiConfiguration,
    KpiConfigurationBinding,
    KpiConfigurationProjection,
)
from ada.web.application.configuration_manager.kpi_authority import (
    KpiConfigurationDefinitionAuthorityProvider,
)


class ProjectionRepository:
    def __init__(self, value=None):
        self.value = value

    def load(self):
        return self.value

    def save(self, projection):
        self.value = projection
        return projection

    def health_check(self):
        return True


def projection() -> KpiConfigurationProjection:
    return KpiConfigurationProjection.create(
        configuration=KpiConfiguration(
            (
                KpiConfigurationBinding(
                    kpi_key='throughput',
                    destination_keys=('global_indicators',),
                    latest_enabled=True,
                    series_enabled=True,
                    series_hours=4,
                ),
                KpiConfigurationBinding(
                    kpi_key='recovery',
                    destination_keys=('plant',),
                ),
            )
        ),
        source_revision='source-r1',
        tool_projection_revision='tool-r1',
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )


def test_bridge_returns_none_when_kpi_configuration_projection_is_absent() -> None:
    provider = KpiConfigurationDefinitionAuthorityProvider(ProjectionRepository())

    assert provider.load() is None


def test_bridge_maps_catalog_to_definition_authority() -> None:
    active = projection()
    provider = KpiConfigurationDefinitionAuthorityProvider(ProjectionRepository(active))

    authority = provider.load()

    assert authority is not None
    assert authority.kpi_configuration_revision == active.revision
    assert authority.kpi_keys == ('throughput', 'recovery')


def test_bridge_does_not_expose_delivery_policy_to_definition() -> None:
    provider = KpiConfigurationDefinitionAuthorityProvider(ProjectionRepository(projection()))

    authority = provider.load()

    assert authority is not None
    assert not hasattr(authority, 'latest_enabled')
    assert not hasattr(authority, 'series_enabled')
    assert not hasattr(authority, 'destination_keys')
