from datetime import UTC, datetime

from ada.configuration.kpi_definition import (
    KpiDefinition,
    KpiDefinitionConfiguration,
    KpiDefinitionProjection,
    KpiDefinitionSourceDocument,
)


def test_kpi_definition_contract_does_not_import_inspection_or_kpi_configuration() -> None:
    import ada.configuration.kpi_definition.contracts as contracts
    import ada.configuration.kpi_definition.models as models
    import ada.configuration.kpi_definition.projection as projection
    import ada.configuration.kpi_definition.source as source

    modules = (contracts, models, projection, source)
    text = '\n'.join(module.__loader__.get_source(module.__name__) or '' for module in modules)

    assert 'ada.web.inspection' not in text
    assert 'ada.configuration.kpis' not in text
    assert 'azure' not in text.lower()
    assert 'cosmos' not in text.lower()


def test_source_and_projection_support_empty_definition_configuration() -> None:
    configuration = KpiDefinitionConfiguration()
    source = KpiDefinitionSourceDocument.create(
        configuration=configuration,
        saved_by='owner',
        saved_at_utc=datetime(2026, 8, 27, 16, 0, tzinfo=UTC),
    )
    projection = KpiDefinitionProjection.create(
        configuration=configuration,
        source_revision=source.revision,
        projected_by='projector',
        projected_at_utc=datetime(2026, 8, 27, 17, 0, tzinfo=UTC),
    )

    assert source.configuration.definitions == ()
    assert projection.configuration.definitions == ()


def test_kpi_definition_is_independent_from_operational_binding_existence() -> None:
    definition = KpiDefinition(
        kpi_key='definition_without_operational_binding',
        fields={'description': 'Independent descriptive metadata'},
    )
    configuration = KpiDefinitionConfiguration((definition,))

    assert configuration.definition(definition.kpi_key) is definition
