from ada.configuration.tools import (
    BrandingVariant,
    ToolConfiguration,
    ToolConfigurationKind,
)
from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.web.configuration.tool_editor import (
    ToolSourceEditorValues,
    build_configuration_from_source_editor,
    source_editor_values_from_configuration,
)


def _configuration() -> ToolConfiguration:
    return ToolConfiguration(
        tool_key='process',
        display_name='Proceso',
        kind=ToolConfigurationKind.PROCESS,
        source_consumption=ToolSourceConsumption(
            tool_key='process',
            source_keys=('pi', 'future_kpi_source'),
        ),
        source_operational_participation=(
            ToolSourceOperationalParticipation(
                tool_key='process',
                control_sources=(
                    SourceControlPolicy('pi', 200, 300),
                ),
                additional_observation_source_keys=(),
            )
        ),
    )


def test_editor_values_load_identity_branding_and_source_state() -> None:
    values = source_editor_values_from_configuration(_configuration())

    assert values.display_name == 'Proceso'
    assert values.kind is ToolConfigurationKind.PROCESS
    assert values.branding_variant is BrandingVariant.ORIGINAL
    assert values.pi_preventive_after_seconds == 200
    assert values.pi_degradation_after_seconds == 300
    assert values.dispatch_enabled is False


def test_editor_can_create_initial_tool_without_existing_document() -> None:
    configuration = build_configuration_from_source_editor(
        base_configuration=None,
        values=ToolSourceEditorValues(
            display_name='Operaciones Integradas',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            branding_variant=BrandingVariant.MINING_MONTH,
            pi_preventive_after_seconds=200,
            pi_degradation_after_seconds=300,
            dispatch_enabled=True,
        ),
    )

    assert configuration.tool_key == 'integrated_operations'
    assert configuration.display_name == 'Operaciones Integradas'
    assert configuration.kind is ToolConfigurationKind.INTEGRATED_OPERATIONS
    assert configuration.branding.variant is BrandingVariant.MINING_MONTH


def test_dispatch_uses_same_operational_thresholds_as_pi() -> None:
    configuration = build_configuration_from_source_editor(
        base_configuration=_configuration(),
        values=ToolSourceEditorValues(
            display_name='Proceso',
            kind=ToolConfigurationKind.PROCESS,
            branding_variant=BrandingVariant.ORIGINAL,
            pi_preventive_after_seconds=250,
            pi_degradation_after_seconds=400,
            dispatch_enabled=True,
        ),
    )

    pi_policy = configuration.source_operational_participation.control_policy('pi')
    dispatch_policy = (
        configuration.source_operational_participation.control_policy('dispatch')
    )

    assert pi_policy is not None
    assert dispatch_policy is not None
    assert dispatch_policy.pre_degrading_after_seconds == (
        pi_policy.pre_degrading_after_seconds
    )
    assert dispatch_policy.degrading_after_seconds == (
        pi_policy.degrading_after_seconds
    )


def test_tool_editor_preserves_non_control_consumption_for_other_domains() -> None:
    configuration = build_configuration_from_source_editor(
        base_configuration=_configuration(),
        values=ToolSourceEditorValues(
            display_name='Proceso',
            kind=ToolConfigurationKind.PROCESS,
            branding_variant=BrandingVariant.ORIGINAL,
            pi_preventive_after_seconds=200,
            pi_degradation_after_seconds=300,
        ),
    )

    assert configuration.source_consumption.source_keys == (
        'pi',
        'future_kpi_source',
    )
    assert (
        configuration
        .source_operational_participation
        .additional_observation_source_keys
        == ()
    )
