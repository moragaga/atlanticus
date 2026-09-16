import pytest

from ada.web.kpis.configuration import (
    KpiConfigurationValidationError,
    KpiDestination,
    KpiDestinationCatalogSnapshot,
    validate_kpi_configuration_destinations,
)

from .helpers import catalog, configuration, tool_target


def test_destination_catalog_is_semantic_and_has_no_private_revision() -> None:
    value = catalog()

    assert value.keys == frozenset({'global_indicators', 'time_status', 'crusher'})
    assert value.destination('crusher') is not None


def test_destination_snapshot_carries_generic_tool_projection_target() -> None:
    target = tool_target()
    snapshot = KpiDestinationCatalogSnapshot(projection_target=target, catalog=catalog())

    assert snapshot.projection_target == target
    assert snapshot.catalog.destination('crusher') == KpiDestination('crusher', 'Chancado')


def test_destination_validation_rejects_destination_not_in_tool_catalog() -> None:
    with pytest.raises(KpiConfigurationValidationError, match="KPI destination 'unknown' is not available"):
        validate_kpi_configuration_destinations(configuration('unknown'), catalog())
