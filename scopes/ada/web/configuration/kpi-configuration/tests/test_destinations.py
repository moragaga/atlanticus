import pytest

from ada.configuration.kpi_configuration import (
    KpiConfigurationValidationError,
    KpiDestination,
    KpiDestinationCatalog,
)


def test_destination_catalog_is_tied_to_tool_projection() -> None:
    catalog = KpiDestinationCatalog(
        tool_projection_revision='tool-r1',
        destinations=(
            KpiDestination('global_indicators', 'Global Indicators'),
            KpiDestination('crusher', 'Chancado'),
        ),
    )
    assert catalog.keys == frozenset({'global_indicators', 'crusher'})
    assert catalog.destination('crusher') is not None


def test_destination_catalog_rejects_duplicate_keys() -> None:
    with pytest.raises(KpiConfigurationValidationError):
        KpiDestinationCatalog(
            tool_projection_revision='tool-r1',
            destinations=(
                KpiDestination('crusher', 'Uno'),
                KpiDestination('crusher', 'Dos'),
            ),
        )
