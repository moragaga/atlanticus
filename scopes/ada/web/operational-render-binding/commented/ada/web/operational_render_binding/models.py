from __future__ import annotations

from dataclasses import dataclass

from ada.configuration.tools import ToolComponent, ToolStructure
from ada.web.component_store import ComponentStoreSnapshot
from ada.web.operational_render_binding.errors import OperationalRenderBindingError


# Une la definición estructural del Component con el Store runtime que le pertenece.
# No copia el payload ni agrega decisiones visuales: sólo conserva ambos contratos juntos.
@dataclass(frozen=True, slots=True)
class OperationalComponentBinding:
    component: ToolComponent
    store: ComponentStoreSnapshot

    def __post_init__(self) -> None:
        # El binding sólo admite contratos canónicos ya validados por sus paquetes propietarios.
        if not isinstance(self.component, ToolComponent):
            raise OperationalRenderBindingError(
                'Operational component binding requires ToolComponent'
            )
        if not isinstance(self.store, ComponentStoreSnapshot):
            raise OperationalRenderBindingError(
                'Operational component binding requires ComponentStoreSnapshot'
            )
        # Un Store nunca puede terminar asociado a otro Component por coincidencia de posición.
        if self.component.key != self.store.component_key:
            raise OperationalRenderBindingError(
                'Operational component binding component key must match Component Store key'
            )


# Es la vista que una composición operacional concreta recibe antes de construir Dash/HTML.
# ToolStructure sigue siendo la autoridad; components sólo empareja cada nodo con su Store.
@dataclass(frozen=True, slots=True)
class OperationalRenderBinding:
    structure: ToolStructure
    components: tuple[OperationalComponentBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.structure, ToolStructure):
            raise OperationalRenderBindingError(
                'Operational render binding requires ToolStructure'
            )
        components = tuple(self.components)
        if any(not isinstance(item, OperationalComponentBinding) for item in components):
            raise OperationalRenderBindingError(
                'Operational render components must contain OperationalComponentBinding values'
            )
        expected_components = self.structure.components
        # La composición debe recibir exactamente un binding por cada Component estructural,
        # incluso cuando su Store esté EMPTY.
        if len(components) != len(expected_components):
            raise OperationalRenderBindingError(
                'Operational render binding must contain one binding per Tool component'
            )
        for expected, binding in zip(expected_components, components, strict=True):
            # El orden lo determina ToolStructure y nunca el orden de llegada de los datos.
            if binding.component != expected:
                raise OperationalRenderBindingError(
                    'Operational render component order must follow Tool Structure'
                )
            if binding.store.tool_key != self.structure.tool_key:
                raise OperationalRenderBindingError(
                    'Operational render Component Store tool key must match Tool Structure'
                )
        object.__setattr__(self, 'components', components)

    @property
    def component_keys(self) -> tuple[str, ...]:
        return tuple(binding.component.key for binding in self.components)
