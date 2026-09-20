import pytest

from ada.web.kpis.registry.errors import KpiRegistryValidationError
from ada.web.kpis.registry.models import KpiRegistry, KpiRegistryBinding


def test_registry_uses_kpi_key_as_authoritative_identity() -> None:
    binding = KpiRegistryBinding(
        kpi_key='throughput',
        destination_keys=('global_indicators',),
    )
    assert binding.to_document()['kpi_key'] == 'throughput'
    assert 'key' not in binding.to_document()
    assert not hasattr(binding, 'to_delivery_document')


def test_registry_round_trip_and_lookup() -> None:
    registry = KpiRegistry(
        (
            KpiRegistryBinding(
                kpi_key='throughput',
                destination_keys=('plant',),
                latest_enabled=True,
                series_enabled=True,
                series_hours=4,
            ),
        )
    )
    restored = KpiRegistry.from_document(registry.to_document())
    assert restored == registry
    assert restored.kpi_keys == frozenset({'throughput'})
    assert restored.binding('throughput') is not None


def test_registry_rejects_duplicate_kpi_keys() -> None:
    binding = KpiRegistryBinding(kpi_key='throughput', destination_keys=('plant',))
    with pytest.raises(KpiRegistryValidationError):
        KpiRegistry((binding, binding))
