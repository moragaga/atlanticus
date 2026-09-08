# Espejo comentado del modelo del editor base de Herramienta.

from __future__ import annotations

from dataclasses import dataclass

from ada.configuration.tools import (
    BrandingConfiguration,
    BrandingVariant,
    ToolConfiguration,
    ToolConfigurationKind,
    validate_ada_operational_tool_sources,
)
from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.web.configuration.tool_editor.errors import (
    ToolSourceEditorValidationError,
)

_CONTROL_SOURCE_KEYS = frozenset({'pi', 'dispatch'})


@dataclass(frozen=True, slots=True)
# La UI edita identidad, branding y estado operacional sin administrar fuentes KPI.
class ToolSourceEditorValues:
    display_name: str
    kind: ToolConfigurationKind
    branding_variant: BrandingVariant
    pi_preventive_after_seconds: int | None
    pi_degradation_after_seconds: int | None
    dispatch_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.display_name, str):
            raise ToolSourceEditorValidationError(
                'Tool display name must be text'
            )
        display_name = self.display_name.strip()
        if not display_name:
            raise ToolSourceEditorValidationError(
                'Tool display name is required'
            )
        if not isinstance(self.kind, ToolConfigurationKind):
            raise ToolSourceEditorValidationError(
                'Tool kind is invalid'
            )
        if self.kind not in {
            ToolConfigurationKind.PROCESS,
            ToolConfigurationKind.INTEGRATED_OPERATIONS,
        }:
            raise ToolSourceEditorValidationError(
                'Tool kind is not supported by this editor'
            )
        if not isinstance(self.branding_variant, BrandingVariant):
            raise ToolSourceEditorValidationError(
                'Tool branding variant is invalid'
            )
        if not isinstance(self.dispatch_enabled, bool):
            raise ToolSourceEditorValidationError(
                'Dispatch enabled flag must be a boolean'
            )
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(
            self,
            'pi_preventive_after_seconds',
            _optional_seconds(
                self.pi_preventive_after_seconds,
                label='PI preventive threshold',
            ),
        )
        object.__setattr__(
            self,
            'pi_degradation_after_seconds',
            _optional_seconds(
                self.pi_degradation_after_seconds,
                label='PI degradation threshold',
            ),
        )


def source_editor_values_from_configuration(
    configuration: ToolConfiguration,
) -> ToolSourceEditorValues:
    participation = configuration.source_operational_participation
    pi_policy = participation.control_policy('pi')
    return ToolSourceEditorValues(
        display_name=configuration.display_name,
        kind=configuration.kind,
        branding_variant=configuration.branding.variant,
        pi_preventive_after_seconds=(
            pi_policy.pre_degrading_after_seconds
            if pi_policy is not None
            else None
        ),
        pi_degradation_after_seconds=(
            pi_policy.degrading_after_seconds
            if pi_policy is not None
            else None
        ),
        dispatch_enabled=configuration.source_consumption.consumes(
            'dispatch'
        ),
    )


# Dispatch hereda los umbrales de PI y se preservan consumos no CONTROL ajenos al editor.
def build_configuration_from_source_editor(
    *,
    base_configuration: ToolConfiguration | None,
    values: ToolSourceEditorValues,
) -> ToolConfiguration:
    tool_key = (
        base_configuration.tool_key
        if base_configuration is not None
        else _initial_tool_key(values.kind)
    )
    pi_policy = SourceControlPolicy(
        source_key='pi',
        pre_degrading_after_seconds=_required_seconds(
            values.pi_preventive_after_seconds,
            label='PI preventive threshold',
        ),
        degrading_after_seconds=_required_seconds(
            values.pi_degradation_after_seconds,
            label='PI degradation threshold',
        ),
    )

    control_sources = [pi_policy]
    source_keys = ['pi']
    if values.dispatch_enabled:
        control_sources.append(
            SourceControlPolicy(
                source_key='dispatch',
                pre_degrading_after_seconds=(
                    pi_policy.pre_degrading_after_seconds
                ),
                degrading_after_seconds=(
                    pi_policy.degrading_after_seconds
                ),
            )
        )
        source_keys.append('dispatch')

    if base_configuration is not None:
        source_keys.extend(
            source_key
            for source_key in (
                base_configuration.source_consumption.source_keys
            )
            if source_key not in _CONTROL_SOURCE_KEYS
        )

    structure = (
        base_configuration.structure
        if (
            base_configuration is not None
            and base_configuration.kind is values.kind
        )
        else None
    )

    configuration = ToolConfiguration(
        tool_key=tool_key,
        display_name=values.display_name,
        kind=values.kind,
        source_consumption=ToolSourceConsumption(
            tool_key=tool_key,
            source_keys=tuple(dict.fromkeys(source_keys)),
        ),
        source_operational_participation=(
            ToolSourceOperationalParticipation(
                tool_key=tool_key,
                control_sources=tuple(control_sources),
                additional_observation_source_keys=(),
            )
        ),
        structure=structure,
        branding=BrandingConfiguration(
            variant=values.branding_variant
        ),
    )
    validate_ada_operational_tool_sources(configuration)
    return configuration


def _initial_tool_key(kind: ToolConfigurationKind) -> str:
    if kind is ToolConfigurationKind.PROCESS:
        return 'process'
    if kind is ToolConfigurationKind.INTEGRATED_OPERATIONS:
        return 'integrated_operations'
    raise ToolSourceEditorValidationError(
        'Tool kind is not supported by this editor'
    )


def _optional_seconds(
    value: object,
    *,
    label: str,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ToolSourceEditorValidationError(
            f'{label} must be an integer'
        )
    if isinstance(value, int):
        resolved = value
    elif isinstance(value, float) and value.is_integer():
        resolved = int(value)
    else:
        raise ToolSourceEditorValidationError(
            f'{label} must be an integer'
        )
    if resolved <= 0:
        raise ToolSourceEditorValidationError(
            f'{label} must be greater than zero'
        )
    return resolved


def _required_seconds(
    value: int | None,
    *,
    label: str,
) -> int:
    if value is None:
        raise ToolSourceEditorValidationError(
            f'{label} is required'
        )
    return value
