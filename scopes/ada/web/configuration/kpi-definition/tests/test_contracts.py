from datetime import UTC, datetime

from ada.configuration.kpi_definition import (
    KpiDefinition,
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionConfiguration,
    KpiDefinitionCoverageStatus,
    KpiDefinitionProjection,
    KpiDefinitionSourceDocument,
)


def authority(*keys: str) -> KpiDefinitionAuthorityCatalog:
    return KpiDefinitionAuthorityCatalog(
        kpi_configuration_revision='kpi-config-r1',
        kpi_keys=tuple(keys),
    )


def test_kpi_definition_uses_authority_contract_without_importing_kpi_configuration() -> None:
    import ada.configuration.kpi_definition.authority as authority_module
    import ada.configuration.kpi_definition.contracts as contracts
    import ada.configuration.kpi_definition.models as models
    import ada.configuration.kpi_definition.projection as projection

    modules = (authority_module, contracts, models, projection)
    text = '\n'.join(module.__loader__.get_source(module.__name__) or '' for module in modules)

    assert 'ada.configuration.kpi_configuration' not in text
    assert 'ada.web.inspection' not in text
    assert 'azure' not in text.lower()
    assert 'cosmos' not in text.lower()


def test_empty_definition_source_projects_virtual_missing_contracts() -> None:
    configuration = KpiDefinitionConfiguration()
    source = KpiDefinitionSourceDocument.create(
        configuration=configuration,
        saved_by='owner',
        saved_at_utc=datetime(2026, 9, 1, 16, 0, tzinfo=UTC),
    )
    projection = KpiDefinitionProjection.create(
        configuration=configuration,
        source_revision=source.revision,
        authority=authority('throughput', 'recovery'),
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 17, 0, tzinfo=UTC),
    )

    assert projection.configuration.definitions == ()
    assert projection.missing_kpi_keys == ('throughput', 'recovery')
    assert all(item.status is KpiDefinitionCoverageStatus.MISSING for item in projection.coverage)


def test_empty_authored_stub_remains_defined_after_projection_roundtrip() -> None:
    configuration = KpiDefinitionConfiguration((KpiDefinition(kpi_key='throughput', fields={}),))
    source = KpiDefinitionSourceDocument.create(
        configuration=configuration,
        saved_by='owner',
        saved_at_utc=datetime(2026, 9, 1, 16, 0, tzinfo=UTC),
    )
    projection = KpiDefinitionProjection.create(
        configuration=configuration,
        source_revision=source.revision,
        authority=authority('throughput'),
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 17, 0, tzinfo=UTC),
    )
    restored = KpiDefinitionProjection.from_document(
        projection.to_document(
            item_id='kpi-definitions',
            partition_key='definitions',
        )
    )

    item = restored.coverage_item('throughput')
    assert item is not None
    assert item.status is KpiDefinitionCoverageStatus.DEFINED
    assert dict(item.fields) == {}
