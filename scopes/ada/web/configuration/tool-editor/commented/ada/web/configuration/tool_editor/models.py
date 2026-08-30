from __future__ import annotations

# Este módulo traduce los controles visuales al contrato backend ya cerrado.
# La UI no crea un modelo alternativo persistente: produce ToolConfiguration válida.

import re
from dataclasses import dataclass

from ada.configuration.tool_source_consumption import ToolSourceConsumption
from ada.configuration.tool_source_operational_participation import (
    SourceControlPolicy,
    ToolSourceOperationalParticipation,
)
from ada.configuration.tools import (
    ToolConfiguration,
    validate_ada_operational_tool_sources,
)
from ada.web.configuration.tool_editor.errors import ToolSourceEditorValidationError

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
_RESERVED_ADDITIONAL_SOURCE_KEYS = frozenset({'pi', 'dispatch'})


@dataclass(frozen=True, slots=True)
class ToolSourceEditorValues:
    pi_pre_degrading_after_seconds: int | None
    pi_degrading_after_seconds: int | None
    dispatch_enabled: bool = False
    dispatch_pre_degrading_after_seconds: int | None = None
    dispatch_degrading_after_seconds: int | None = None
    additional_observation_source_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'pi_pre_degrading_after_seconds',
            _optional_seconds(
                self.pi_pre_degrading_after_seconds,
                label='PI pre-degrading threshold',
            ),
        )
        object.__setattr__(
            self,
            'pi_degrading_after_seconds',
            _optional_seconds(
                self.pi_degrading_after_seconds,
                label='PI degrading threshold',
            ),
        )
        if not isinstance(self.dispatch_enabled, bool):
            raise ToolSourceEditorValidationError('Dispatch enabled flag must be a boolean')
        object.__setattr__(
            self,
            'dispatch_pre_degrading_after_seconds',
            _optional_seconds(
                self.dispatch_pre_degrading_after_seconds,
                label='Dispatch pre-degrading threshold',
            ),
        )
        object.__setattr__(
            self,
            'dispatch_degrading_after_seconds',
            _optional_seconds(
                self.dispatch_degrading_after_seconds,
                label='Dispatch degrading threshold',
            ),
        )
        normalized_additional = _normalize_source_keys(
            self.additional_observation_source_keys
        )
        reserved = next(
            (
                source_key
                for source_key in normalized_additional
                if source_key in _RESERVED_ADDITIONAL_SOURCE_KEYS
            ),
            None,
        )
        if reserved is not None:
            raise ToolSourceEditorValidationError(
                f'Additional Observation source must not duplicate CONTROL source: {reserved!r}'
            )
        object.__setattr__(
            self,
            'additional_observation_source_keys',
            normalized_additional,
        )


def source_editor_values_from_configuration(
    configuration: ToolConfiguration,
) -> ToolSourceEditorValues:
    participation = configuration.source_operational_participation
    pi_policy = participation.control_policy('pi')
    dispatch_policy = participation.control_policy('dispatch')
    return ToolSourceEditorValues(
        pi_pre_degrading_after_seconds=(
            pi_policy.pre_degrading_after_seconds if pi_policy is not None else None
        ),
        pi_degrading_after_seconds=(
            pi_policy.degrading_after_seconds if pi_policy is not None else None
        ),
        dispatch_enabled=configuration.source_consumption.consumes('dispatch'),
        dispatch_pre_degrading_after_seconds=(
            dispatch_policy.pre_degrading_after_seconds
            if dispatch_policy is not None
            else None
        ),
        dispatch_degrading_after_seconds=(
            dispatch_policy.degrading_after_seconds if dispatch_policy is not None else None
        ),
        additional_observation_source_keys=(
            participation.additional_observation_source_keys
        ),
    )


def parse_additional_observation_source_keys(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, str):
        raise ToolSourceEditorValidationError(
            'Additional Observation sources must be provided as text'
        )
    raw_values = re.split(r'[,\n]', value)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        source_key = raw_value.strip().casefold()
        if not source_key:
            continue
        if not _KEY_PATTERN.fullmatch(source_key):
            raise ToolSourceEditorValidationError(
                f'Additional Observation source key has an invalid format: {source_key!r}'
            )
        if source_key in _RESERVED_ADDITIONAL_SOURCE_KEYS:
            raise ToolSourceEditorValidationError(
                f'Additional Observation source must not duplicate CONTROL source: {source_key!r}'
            )
        if source_key not in seen:
            normalized.append(source_key)
            seen.add(source_key)
    return tuple(normalized)


def build_configuration_from_source_editor(
    *,
    base_configuration: ToolConfiguration,
    values: ToolSourceEditorValues,
) -> ToolConfiguration:
    pi_policy = SourceControlPolicy(
        source_key='pi',
        pre_degrading_after_seconds=_required_seconds(
            values.pi_pre_degrading_after_seconds,
            label='PI pre-degrading threshold',
        ),
        degrading_after_seconds=_required_seconds(
            values.pi_degrading_after_seconds,
            label='PI degrading threshold',
        ),
    )
    control_sources = [pi_policy]
    source_keys = ['pi']
    if values.dispatch_enabled:
        control_sources.append(
            SourceControlPolicy(
                source_key='dispatch',
                pre_degrading_after_seconds=_required_seconds(
                    values.dispatch_pre_degrading_after_seconds,
                    label='Dispatch pre-degrading threshold',
                ),
                degrading_after_seconds=_required_seconds(
                    values.dispatch_degrading_after_seconds,
                    label='Dispatch degrading threshold',
                ),
            )
        )
        source_keys.append('dispatch')
    source_keys.extend(values.additional_observation_source_keys)
    configuration = ToolConfiguration(
        tool_key=base_configuration.tool_key,
        display_name=base_configuration.display_name,
        kind=base_configuration.kind,
        source_consumption=ToolSourceConsumption(
            tool_key=base_configuration.tool_key,
            source_keys=tuple(source_keys),
        ),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key=base_configuration.tool_key,
            control_sources=tuple(control_sources),
            additional_observation_source_keys=(
                values.additional_observation_source_keys
            ),
        ),
    )
    validate_ada_operational_tool_sources(configuration)
    return configuration


def _optional_seconds(value: object, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ToolSourceEditorValidationError(f'{label} must be an integer')
    if isinstance(value, int):
        resolved = value
    elif isinstance(value, float) and value.is_integer():
        resolved = int(value)
    else:
        raise ToolSourceEditorValidationError(f'{label} must be an integer')
    if resolved <= 0:
        raise ToolSourceEditorValidationError(f'{label} must be greater than zero')
    return resolved


def _required_seconds(value: int | None, *, label: str) -> int:
    if value is None:
        raise ToolSourceEditorValidationError(f'{label} is required')
    return value


def _normalize_source_keys(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise ToolSourceEditorValidationError(
            'Additional Observation source keys must be a collection'
        )
    try:
        raw_values = tuple(value)
    except TypeError as error:
        raise ToolSourceEditorValidationError(
            'Additional Observation source keys must be a collection'
        ) from error
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        if not isinstance(raw_value, str):
            raise ToolSourceEditorValidationError(
                'Additional Observation source key must be a string'
            )
        source_key = raw_value.strip().casefold()
        if not _KEY_PATTERN.fullmatch(source_key):
            raise ToolSourceEditorValidationError(
                f'Additional Observation source key has an invalid format: {source_key!r}'
            )
        if source_key not in seen:
            normalized.append(source_key)
            seen.add(source_key)
    return tuple(normalized)
