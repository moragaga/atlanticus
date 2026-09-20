import pytest

from ada.web.kpis.definition.coverage import (
    KpiDefinitionCatalog,
    KpiDefinitionCoverageStatus,
    build_kpi_definition_coverage,
    validate_kpi_definition_configuration,
)
from ada.web.kpis.definition.errors import KpiDefinitionValidationError
from ada.web.kpis.definition.models import KpiDefinition, KpiDefinitionConfiguration
from ada.web.kpis.registry.models import KpiRegistry, KpiRegistryBinding


def _registry(*keys: str) -> KpiRegistry:
    return KpiRegistry(
        tuple(KpiRegistryBinding(kpi_key=key, destination_keys=('crusher',)) for key in keys)
    )


def _configuration(*keys: str) -> KpiDefinitionConfiguration:
    return KpiDefinitionConfiguration(
        tuple(KpiDefinition(kpi_key=key, fields={'detail': f'Detail {key}'}) for key in keys)
    )


def test_coverage_uses_kpi_registry_keys_as_authority() -> None:
    coverage = build_kpi_definition_coverage(
        _configuration('defined'),
        _registry('defined', 'missing'),
    )
    assert tuple((item.kpi_key, item.status) for item in coverage) == (
        ('defined', KpiDefinitionCoverageStatus.DEFINED),
        ('missing', KpiDefinitionCoverageStatus.MISSING),
    )


def test_missing_definition_is_valid_for_projection() -> None:
    validate_kpi_definition_configuration(
        _configuration('defined'),
        _registry('defined', 'missing'),
    )


def test_orphan_definition_is_rejected() -> None:
    with pytest.raises(KpiDefinitionValidationError, match="'orphan' is not configured"):
        validate_kpi_definition_configuration(
            _configuration('defined', 'orphan'),
            _registry('defined'),
        )


def test_projected_catalog_document_roundtrip_preserves_coverage() -> None:
    configuration = _configuration('defined')
    catalog = KpiDefinitionCatalog(
        configuration=configuration,
        coverage=build_kpi_definition_coverage(configuration, _registry('defined', 'missing')),
    )
    assert KpiDefinitionCatalog.from_document(catalog.to_document()) == catalog
