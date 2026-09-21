from __future__ import annotations

from dataclasses import dataclass

from ada.web.operational_render_binding.errors import OperationalRenderBindingError
from ada.web.tools.structure import ToolComponent, ToolStructure


# Representa únicamente la existencia estructural de un ToolComponent dentro del render.
# Los datos runtime pertenecen a las superficies de consumo que los publican, no a este binding.
@dataclass(frozen=True, slots=True)
class OperationalComponentBinding:
    component: ToolComponent

    def __post_init__(self) -> None:
        if not isinstance(self.component, ToolComponent):
            raise OperationalRenderBindingError(
                'Operational component binding requires ToolComponent'
            )


# ToolStructure es la única autoridad del árbol que el render puede materializar.
# El binding no contiene snapshots, payloads ni referencias a una capability de datos concreta.
@dataclass(frozen=True, slots=True)
class OperationalRenderBinding:
    structure: ToolStructure
    components: tuple[OperationalComponentBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.structure, ToolStructure):
            raise OperationalRenderBindingError('Operational render binding requires ToolStructure')
        components = tuple(self.components)
        if any(not isinstance(item, OperationalComponentBinding) for item in components):
            raise OperationalRenderBindingError(
                'Operational render components must contain OperationalComponentBinding values'
            )
        expected_components = self.structure.components
        # Cada componente configurado debe tener exactamente una posición estructural.
        if len(components) != len(expected_components):
            raise OperationalRenderBindingError(
                'Operational render binding must contain one binding per Tool component'
            )
        for expected, binding in zip(expected_components, components, strict=True):
            # El orden siempre procede de ToolStructure y no del orden de llegada de datos.
            if binding.component != expected:
                raise OperationalRenderBindingError(
                    'Operational render component order must follow Tool Structure'
                )
        object.__setattr__(self, 'components', components)

    @property
    def component_keys(self) -> tuple[str, ...]:
        return tuple(binding.component.key for binding in self.components)
