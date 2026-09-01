from datetime import UTC, datetime, timedelta

from ada.kpis.delivery import (
    KpiDeliveryBinding,
    KpiDeliveryConfiguration,
    KpiDeliveryStatus,
    KpiLatestValue,
    project_kpi_latest,
)


def _configuration() -> KpiDeliveryConfiguration:
    return KpiDeliveryConfiguration(
        revision='cfg-1',
        tool_projection_revision='tool-1',
        bindings=(
            KpiDeliveryBinding(
                key='production',
                destination_keys=('global_indicators', 'milling'),
                latest_enabled=True,
                series_enabled=True,
                series_hours=1,
            ),
            KpiDeliveryBinding(
                key='availability',
                destination_keys=('global_indicators',),
                latest_enabled=True,
                series_enabled=False,
            ),
            KpiDeliveryBinding(
                key='series_only',
                destination_keys=('milling',),
                latest_enabled=False,
                series_enabled=True,
                series_hours=3,
            ),
        ),
    )


def test_latest_routes_once_per_destination_and_excludes_latest_disabled() -> None:
    snapshot = project_kpi_latest(
        configuration=_configuration(),
        values={
            'production': KpiLatestValue(KpiDeliveryStatus.OK, 'value', '66,00'),
            'availability': KpiLatestValue(KpiDeliveryStatus.ERROR, 'value', None),
        },
        watermark_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        published_at_utc=datetime(2026, 9, 1, 12, 0, 1, tzinfo=UTC),
    )
    payload = snapshot.to_payload()
    assert payload['destinations']['global_indicators']['production']['value'] == '66,00'
    assert payload['destinations']['milling']['production']['value'] == '66,00'
    assert payload['destinations']['global_indicators']['availability']['status'] == 'error'
    assert 'series_only' not in payload['destinations']['milling']


def test_latest_generates_missing_for_configured_key_without_value() -> None:
    snapshot = project_kpi_latest(
        configuration=_configuration(),
        values={'production': KpiLatestValue(KpiDeliveryStatus.OK, 'value', 66)},
        watermark_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        published_at_utc=datetime(2026, 9, 1, 12, 0, 1, tzinfo=UTC),
    )
    missing = snapshot.to_payload()['destinations']['global_indicators']['availability']
    assert missing == {'status': 'missing', 'value_kind': None, 'value': None}


def test_latest_empty_when_no_binding_has_latest_enabled() -> None:
    configuration = KpiDeliveryConfiguration(
        revision='cfg-1',
        bindings=(
            KpiDeliveryBinding(
                key='production',
                destination_keys=('global_indicators',),
                latest_enabled=False,
                series_enabled=False,
            ),
        ),
    )
    snapshot = project_kpi_latest(
        configuration=configuration,
        values={},
        watermark_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        published_at_utc=datetime(2026, 9, 1, 12, 0, 1, tzinfo=UTC),
    )
    assert snapshot.destinations == {}


def test_latest_revision_is_deterministic_and_ignores_published_at() -> None:
    args = {
        'configuration': _configuration(),
        'values': {'production': KpiLatestValue(KpiDeliveryStatus.OK, 'value', 66)},
        'watermark_utc': datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    }
    first = project_kpi_latest(
        **args,
        published_at_utc=datetime(2026, 9, 1, 12, 0, 1, tzinfo=UTC),
    )
    second = project_kpi_latest(
        **args,
        published_at_utc=datetime(2026, 9, 1, 12, 5, tzinfo=UTC),
    )
    assert first.manifest.revision == second.manifest.revision


def test_latest_revision_changes_for_new_watermark_even_with_same_value() -> None:
    values = {'production': KpiLatestValue(KpiDeliveryStatus.OK, 'value', 66)}
    base = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    first = project_kpi_latest(
        configuration=_configuration(),
        values=values,
        watermark_utc=base,
        published_at_utc=base,
    )
    second = project_kpi_latest(
        configuration=_configuration(),
        values=values,
        watermark_utc=base + timedelta(seconds=1),
        published_at_utc=base + timedelta(seconds=1),
    )
    assert first.manifest.revision != second.manifest.revision


def test_latest_revision_changes_for_configuration_revision() -> None:
    first_configuration = _configuration()
    second_configuration = KpiDeliveryConfiguration(
        revision='cfg-2',
        tool_projection_revision=first_configuration.tool_projection_revision,
        bindings=first_configuration.bindings,
    )
    values = {'production': KpiLatestValue(KpiDeliveryStatus.OK, 'value', 66)}
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    first = project_kpi_latest(
        configuration=first_configuration,
        values=values,
        watermark_utc=now,
        published_at_utc=now,
    )
    second = project_kpi_latest(
        configuration=second_configuration,
        values=values,
        watermark_utc=now,
        published_at_utc=now,
    )
    assert first.manifest.revision != second.manifest.revision
