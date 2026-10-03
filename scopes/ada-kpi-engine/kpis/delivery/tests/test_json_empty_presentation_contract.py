from datetime import UTC, datetime

from ada.kpis.delivery import (
    KpiDeliveryBinding,
    KpiDeliveryConfiguration,
    KpiDeliveryStatus,
    KpiLatestValue,
    project_kpi_latest,
)


def test_latest_preserves_degraded_json_structure() -> None:
    configuration = KpiDeliveryConfiguration(
        revision='cfg-json',
        bindings=(
            KpiDeliveryBinding(
                key='dynamic',
                destination_keys=('component',),
                latest_enabled=True,
                series_enabled=False,
            ),
        ),
    )
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    for status in (KpiDeliveryStatus.MISSING, KpiDeliveryStatus.ERROR):
        snapshot = project_kpi_latest(
            configuration=configuration,
            values={
                'dynamic': KpiLatestValue(
                    status=status,
                    value_kind='json',
                    value={'rows': [], 'columns': []},
                )
            },
            watermark_utc=now,
            published_at_utc=now,
        )
        value = snapshot.destinations['component']['dynamic']
        assert value.status is status
        assert value.value_kind == 'json'
        assert value.value == {'rows': [], 'columns': []}
