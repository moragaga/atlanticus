import pytest

from ada.configuration.kpi_configuration import (
    KpiConfiguration,
    KpiConfigurationBinding,
    KpiConfigurationValidationError,
)


def test_administrative_identity_is_kpi_key() -> None:
    binding = KpiConfigurationBinding(
        kpi_key='throughput',
        destination_keys=('global_indicators',),
    )
    assert binding.to_document()['kpi_key'] == 'throughput'
    assert 'key' not in binding.to_document()
    assert binding.to_delivery_document()['key'] == 'throughput'


def test_binding_requires_at_least_one_destination() -> None:
    with pytest.raises(KpiConfigurationValidationError):
        KpiConfigurationBinding(kpi_key='throughput', destination_keys=())


def test_binding_rejects_duplicate_destinations() -> None:
    with pytest.raises(KpiConfigurationValidationError):
        KpiConfigurationBinding(
            kpi_key='throughput',
            destination_keys=('plant', 'plant'),
        )


def test_series_contract_is_strict_and_bounded() -> None:
    with pytest.raises(KpiConfigurationValidationError):
        KpiConfigurationBinding(
            kpi_key='throughput',
            destination_keys=('plant',),
            series_enabled=True,
        )
    with pytest.raises(KpiConfigurationValidationError):
        KpiConfigurationBinding(
            kpi_key='throughput',
            destination_keys=('plant',),
            series_enabled=True,
            series_hours=25,
        )
    with pytest.raises(KpiConfigurationValidationError):
        KpiConfigurationBinding(
            kpi_key='throughput',
            destination_keys=('plant',),
            series_enabled=False,
            series_hours=4,
        )


def test_configuration_rejects_duplicate_kpi_keys() -> None:
    binding = KpiConfigurationBinding(
        kpi_key='throughput',
        destination_keys=('plant',),
    )
    with pytest.raises(KpiConfigurationValidationError):
        KpiConfiguration((binding, binding))


def test_configuration_round_trip_and_lookup() -> None:
    configuration = KpiConfiguration(
        (
            KpiConfigurationBinding(
                kpi_key='throughput',
                destination_keys=('plant',),
                latest_enabled=True,
                series_enabled=True,
                series_hours=4,
            ),
        )
    )
    restored = KpiConfiguration.from_document(configuration.to_document())
    assert restored == configuration
    assert restored.kpi_keys == frozenset({'throughput'})
    assert restored.binding('throughput') is not None
