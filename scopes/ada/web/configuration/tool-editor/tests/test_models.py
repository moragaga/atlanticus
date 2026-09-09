from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.configuration.tools import (
    BrandingVariant,
    ToolConfiguration,
    ToolConfigurationKind,
)
from ada.web.configuration.tool_editor import (
    ToolSourceEditorValues,
    build_configuration_from_source_editor,
    source_editor_values_from_configuration,
)
from ada.web.configuration.tool_editor.models import (
    generate_named_key,
    generate_tool_key,
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
                control_sources=(SourceControlPolicy('pi', 200, 300),),
                additional_observation_source_keys=(),
            )
        ),
    )


def _configuration_with_dispatch() -> ToolConfiguration:
    return ToolConfiguration(
        tool_key='process',
        display_name='Proceso',
        kind=ToolConfigurationKind.PROCESS,
        source_consumption=ToolSourceConsumption(
            tool_key='process',
            source_keys=('pi', 'dispatch'),
        ),
        source_operational_participation=(
            ToolSourceOperationalParticipation(
                tool_key='process',
                control_sources=(
                    SourceControlPolicy('pi', 200, 300),
                    SourceControlPolicy('dispatch', 350, 500),
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
    assert values.dispatch_preventive_after_seconds is None
    assert values.dispatch_degradation_after_seconds is None


def test_editor_values_preserve_independent_dispatch_thresholds() -> None:
    values = source_editor_values_from_configuration(_configuration_with_dispatch())

    assert values.pi_preventive_after_seconds == 200
    assert values.pi_degradation_after_seconds == 300
    assert values.dispatch_enabled is True
    assert values.dispatch_preventive_after_seconds == 350
    assert values.dispatch_degradation_after_seconds == 500


def test_editor_can_create_initial_tool_without_existing_document() -> None:
    configuration = build_configuration_from_source_editor(
        base_configuration=None,
        tool_key='tool_operaciones_integradas_a1b2c3d4e5f6',
        values=ToolSourceEditorValues(
            display_name='Operaciones Integradas',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            branding_variant=BrandingVariant.MINING_MONTH,
            pi_preventive_after_seconds=200,
            pi_degradation_after_seconds=300,
            dispatch_enabled=True,
            dispatch_preventive_after_seconds=350,
            dispatch_degradation_after_seconds=450,
        ),
    )

    assert configuration.tool_key == 'tool_operaciones_integradas_a1b2c3d4e5f6'
    assert configuration.display_name == 'Operaciones Integradas'
    assert configuration.kind is ToolConfigurationKind.INTEGRATED_OPERATIONS
    assert configuration.branding.variant is BrandingVariant.MINING_MONTH
    dispatch_policy = configuration.source_operational_participation.control_policy('dispatch')
    assert dispatch_policy is not None
    assert dispatch_policy.pre_degrading_after_seconds == 350
    assert dispatch_policy.degrading_after_seconds == 450


def test_dispatch_uses_its_own_preventive_and_degradation_thresholds() -> None:
    configuration = build_configuration_from_source_editor(
        base_configuration=_configuration(),
        tool_key=None,
        values=ToolSourceEditorValues(
            display_name='Proceso',
            kind=ToolConfigurationKind.PROCESS,
            branding_variant=BrandingVariant.ORIGINAL,
            pi_preventive_after_seconds=250,
            pi_degradation_after_seconds=400,
            dispatch_enabled=True,
            dispatch_preventive_after_seconds=600,
            dispatch_degradation_after_seconds=700,
        ),
    )

    pi_policy = configuration.source_operational_participation.control_policy('pi')
    dispatch_policy = configuration.source_operational_participation.control_policy('dispatch')

    assert pi_policy is not None
    assert dispatch_policy is not None
    assert pi_policy.pre_degrading_after_seconds == 250
    assert pi_policy.degrading_after_seconds == 400
    assert dispatch_policy.pre_degrading_after_seconds == 600
    assert dispatch_policy.degrading_after_seconds == 700


def test_tool_editor_preserves_non_control_consumption_for_other_domains() -> None:
    configuration = build_configuration_from_source_editor(
        base_configuration=_configuration(),
        tool_key=None,
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
    assert configuration.source_operational_participation.additional_observation_source_keys == ()


def test_generated_tool_key_is_ascii_readable_and_unique() -> None:
    first = generate_tool_key('Área Húmeda – Flotación Ñandú')
    second = generate_tool_key('Área Húmeda – Flotación Ñandú')

    assert first.startswith('tool_area_humeda_flotacion_nandu_')
    assert second.startswith('tool_area_humeda_flotacion_nandu_')
    assert first != second
    assert first.isascii()
    assert 'á' not in first
    assert 'ñ' not in first


def test_new_tool_identity_does_not_depend_on_tool_kind() -> None:
    tool_key = 'tool_flotacion_74bc3319a120'
    configuration = build_configuration_from_source_editor(
        base_configuration=None,
        tool_key=tool_key,
        values=ToolSourceEditorValues(
            display_name='Flotación',
            kind=ToolConfigurationKind.PROCESS,
            branding_variant=BrandingVariant.ORIGINAL,
            pi_preventive_after_seconds=200,
            pi_degradation_after_seconds=300,
        ),
    )

    assert configuration.tool_key == tool_key
    assert configuration.kind is ToolConfigurationKind.PROCESS


def test_component_and_subcomponent_keys_are_readable_ascii_and_unique() -> None:
    component_a = generate_named_key('cmp', 'Carguío Área Húmeda')
    component_b = generate_named_key(
        'cmp',
        'Carguío Área Húmeda',
        existing=[component_a],
    )
    subcomponent = generate_named_key('sub', 'Extracción N° 1')

    assert component_a.startswith('cmp_carguio_area_humeda_')
    assert component_b.startswith('cmp_carguio_area_humeda_')
    assert component_a != component_b
    assert subcomponent.startswith('sub_extraccion_n_1_')
    assert component_a.isascii()
    assert subcomponent.isascii()
