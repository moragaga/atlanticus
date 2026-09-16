import pytest

from ada.web.kpis.definition import (
    KpiDefinitionCoverageStatus,
    KpiDefinitionValidationError,
    build_kpi_definition_coverage,
    validate_kpi_definition_configuration,
)

from .helpers import definition_configuration, kpi_configuration


def test_coverage_uses_kpi_configuration_keys_as_authority() -> None:
    coverage = build_kpi_definition_coverage(
        definition_configuration('defined'),
        kpi_configuration('defined', 'missing'),
    )

    assert tuple((item.kpi_key, item.status) for item in coverage) == (
        ('defined', KpiDefinitionCoverageStatus.DEFINED),
        ('missing', KpiDefinitionCoverageStatus.MISSING),
    )


def test_missing_definition_is_valid_for_projection() -> None:
    validate_kpi_definition_configuration(
        definition_configuration('defined'),
        kpi_configuration('defined', 'missing'),
    )


def test_orphan_definition_is_rejected() -> None:
    with pytest.raises(KpiDefinitionValidationError, match="'orphan' is not configured"):
        validate_kpi_definition_configuration(
            definition_configuration('defined', 'orphan'),
            kpi_configuration('defined'),
        )
