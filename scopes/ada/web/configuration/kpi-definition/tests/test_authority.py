from ada.configuration.kpi_definition import (
    KpiDefinition,
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionConfiguration,
    KpiDefinitionCoverageStatus,
    build_kpi_definition_coverage,
)


def test_missing_definition_and_empty_authored_definition_are_distinct() -> None:
    configuration = KpiDefinitionConfiguration(
        (
            KpiDefinition(
                kpi_key='throughput',
                fields={},
            ),
        )
    )
    authority = KpiDefinitionAuthorityCatalog(
        kpi_configuration_revision='kpi-config-r1',
        kpi_keys=('throughput', 'recovery'),
    )

    coverage = build_kpi_definition_coverage(configuration, authority)

    assert coverage[0].kpi_key == 'throughput'
    assert coverage[0].status is KpiDefinitionCoverageStatus.DEFINED
    assert dict(coverage[0].fields) == {}
    assert coverage[1].kpi_key == 'recovery'
    assert coverage[1].status is KpiDefinitionCoverageStatus.MISSING
    assert dict(coverage[1].fields) == {}


def test_authority_preserves_kpi_configuration_order() -> None:
    authority = KpiDefinitionAuthorityCatalog(
        kpi_configuration_revision='kpi-config-r1',
        kpi_keys=('recovery', 'throughput'),
    )

    assert authority.kpi_keys == ('recovery', 'throughput')
