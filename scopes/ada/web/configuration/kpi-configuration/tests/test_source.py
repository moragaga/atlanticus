from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_configuration import (
    KpiConfiguration,
    KpiConfigurationBinding,
    KpiConfigurationSourceDocument,
    KpiConfigurationValidationError,
    build_kpi_configuration_digest,
)


def _configuration() -> KpiConfiguration:
    return KpiConfiguration(
        (
            KpiConfigurationBinding(
                kpi_key='throughput',
                destination_keys=('crusher',),
            ),
        )
    )


def test_source_round_trip_uses_canonical_digest() -> None:
    configuration = _configuration()
    document = KpiConfigurationSourceDocument.create(
        configuration=configuration,
        saved_by='admin',
        saved_at_utc=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert document.revision == build_kpi_configuration_digest(configuration)
    assert KpiConfigurationSourceDocument.from_document(document.to_document()) == document


def test_source_rejects_wrong_revision() -> None:
    with pytest.raises(KpiConfigurationValidationError):
        KpiConfigurationSourceDocument(
            configuration=_configuration(),
            revision='wrong',
            saved_by='admin',
            saved_at_utc=datetime(2026, 9, 1, tzinfo=UTC),
        )
