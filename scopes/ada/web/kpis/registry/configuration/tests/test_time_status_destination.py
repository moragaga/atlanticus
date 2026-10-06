import pytest

from ada.web.kpis.registry.configuration import (
    KpiDestination,
    KpiDestinationCatalog,
    KpiRegistryValidationError,
    validate_kpi_registry_destinations,
)
from ada.web.kpis.registry.models import KpiRegistry, KpiRegistryBinding


def _catalog() -> KpiDestinationCatalog:
    return KpiDestinationCatalog(
        destinations=(
            KpiDestination('time_status', 'Time Status'),
            KpiDestination('crusher', 'Chancado'),
        )
    )


def test_time_status_destination_accepts_latest_only_binding() -> None:
    registry = KpiRegistry(
        bindings=(
            KpiRegistryBinding(
                kpi_key='pi',
                destination_keys=('time_status',),
                latest_enabled=True,
                series_enabled=False,
            ),
        )
    )

    validate_kpi_registry_destinations(registry, _catalog())


def test_time_status_destination_rejects_series_delivery() -> None:
    registry = KpiRegistry(
        bindings=(
            KpiRegistryBinding(
                kpi_key='pi',
                destination_keys=('time_status',),
                latest_enabled=True,
                series_enabled=True,
                series_hours=1,
            ),
        )
    )

    with pytest.raises(KpiRegistryValidationError, match='does not support series delivery'):
        validate_kpi_registry_destinations(registry, _catalog())


def test_component_destination_still_accepts_series_delivery() -> None:
    registry = KpiRegistry(
        bindings=(
            KpiRegistryBinding(
                kpi_key='throughput',
                destination_keys=('crusher',),
                latest_enabled=True,
                series_enabled=True,
                series_hours=1,
            ),
        )
    )

    validate_kpi_registry_destinations(registry, _catalog())
