from __future__ import annotations

from dataclasses import dataclass

from ada.web.operational_render_binding.errors import OperationalRenderBindingError
from ada.contracts.tools.enums import ToolConfigurationKind
from ada.contracts.tools.errors import ToolConfigurationValidationError
from ada.contracts.tools.structure import ToolComponent, ToolStructure
from ada.contracts.tools.validation import require_key


@dataclass(frozen=True, slots=True)
class OperationalComponentBinding:
    component: ToolComponent

    def __post_init__(self) -> None:
        if not isinstance(self.component, ToolComponent):
            raise OperationalRenderBindingError(
                'Operational component binding requires ToolComponent'
            )


@dataclass(frozen=True, slots=True)
class OperationalRenderBinding:
    structure: ToolStructure
    components: tuple[OperationalComponentBinding, ...]
    bottom_component_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.structure, ToolStructure):
            raise OperationalRenderBindingError('Operational render binding requires ToolStructure')
        components = tuple(self.components)
        if any(not isinstance(item, OperationalComponentBinding) for item in components):
            raise OperationalRenderBindingError(
                'Operational render components must contain OperationalComponentBinding values'
            )
        expected_components = self.structure.components
        if len(components) != len(expected_components):
            raise OperationalRenderBindingError(
                'Operational render binding must contain one binding per Tool component'
            )
        for expected, binding in zip(expected_components, components, strict=True):
            if binding.component != expected:
                raise OperationalRenderBindingError(
                    'Operational render component order must follow Tool Structure'
                )
        bottom_component_key = self.bottom_component_key
        if bottom_component_key is not None:
            try:
                bottom_component_key = require_key(
                    bottom_component_key,
                    label='Operational render bottom component key',
                )
            except ToolConfigurationValidationError as error:
                raise OperationalRenderBindingError(str(error)) from error
            if self.structure.kind is not ToolConfigurationKind.PROCESS:
                raise OperationalRenderBindingError(
                    'Operational render bottom component is only supported for Process'
                )
            if bottom_component_key not in {
                binding.component.key for binding in components
            }:
                raise OperationalRenderBindingError(
                    'Operational render bottom component must reference a Tool component'
                )
            if bottom_component_key == self.structure.center_component_key:
                raise OperationalRenderBindingError(
                    'Operational render bottom component must differ from Process center component'
                )
        object.__setattr__(self, 'components', components)
        object.__setattr__(self, 'bottom_component_key', bottom_component_key)

    @property
    def component_keys(self) -> tuple[str, ...]:
        return tuple(binding.component.key for binding in self.components)

    @property
    def main_components(self) -> tuple[OperationalComponentBinding, ...]:
        return tuple(
            binding
            for binding in self.components
            if binding.component.key != self.bottom_component_key
        )

    @property
    def main_component_keys(self) -> tuple[str, ...]:
        return tuple(binding.component.key for binding in self.main_components)

    @property
    def bottom_component(self) -> OperationalComponentBinding | None:
        if self.bottom_component_key is None:
            return None
        return next(
            binding
            for binding in self.components
            if binding.component.key == self.bottom_component_key
        )
