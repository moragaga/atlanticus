import pytest

from ada.kpis.delivery import (
    KpiDeliveryBinding,
    KpiDeliveryConfiguration,
    KpiDeliveryValidationError,
)


def test_binding_accepts_disabled_delivery_with_owned_destinations() -> None:
    binding = KpiDeliveryBinding(
        key='production',
        destination_keys=('global_indicators',),
        latest_enabled=False,
        series_enabled=False,
    )
    assert binding.series_hours is None


def test_binding_requires_destination() -> None:
    with pytest.raises(KpiDeliveryValidationError, match='at least one destination'):
        KpiDeliveryBinding(
            key='production',
            destination_keys=(),
            latest_enabled=True,
            series_enabled=False,
        )


def test_binding_rejects_duplicate_destinations() -> None:
    with pytest.raises(KpiDeliveryValidationError, match='duplicates'):
        KpiDeliveryBinding(
            key='production',
            destination_keys=('global_indicators', 'global_indicators'),
            latest_enabled=True,
            series_enabled=False,
        )


def test_series_requires_hours_and_supports_24_hours() -> None:
    with pytest.raises(KpiDeliveryValidationError, match='required'):
        KpiDeliveryBinding(
            key='production',
            destination_keys=('global_indicators',),
            latest_enabled=False,
            series_enabled=True,
        )
    binding = KpiDeliveryBinding(
        key='production',
        destination_keys=('global_indicators',),
        latest_enabled=False,
        series_enabled=True,
        series_hours=24,
    )
    assert binding.series_hours == 24


def test_configuration_rejects_duplicate_kpi_keys() -> None:
    binding = KpiDeliveryBinding(
        key='production',
        destination_keys=('global_indicators',),
        latest_enabled=True,
        series_enabled=False,
    )
    with pytest.raises(KpiDeliveryValidationError, match='duplicate KPI keys'):
        KpiDeliveryConfiguration(revision='cfg-1', bindings=(binding, binding))
