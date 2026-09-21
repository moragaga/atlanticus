# Read model de referencias Tool para el authoring de Alarm Configuration.
# No valida ni resuelve Alarm Configuration: sólo traduce el Tool Catalog CURRENT
# a opciones que la futura UI podrá presentar sin consultar los Cosmos individuales.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.tools.enums import ToolConfigurationKind
from ada_command_center.tools.catalog import ToolCatalogEntry, ToolCatalogStore
from atlanticus.web.source.models import SourceReleaseId


# Dirección persistible de un subcomponente visible desde un componente.
# owner_component_key conserva el owner real incluso cuando la visibilidad viene por linked_component_keys.
@dataclass(frozen=True, slots=True)
class AlarmToolSubcomponentReference:
    owner_component_key: str
    subcomponent_key: str
    display_name: str


# Componente mostrado al configurador de alarmas con sus subcomponentes visibles.
@dataclass(frozen=True, slots=True)
class AlarmToolComponentReference:
    component_key: str
    display_name: str
    subcomponents: tuple[AlarmToolSubcomponentReference, ...]


# Tool disponible para authoring y provenance de la revisión Tool que originó esta opción.
@dataclass(frozen=True, slots=True)
class AlarmToolReference:
    tool_key: str
    display_name: str
    kind: ToolConfigurationKind
    source_release_id: SourceReleaseId
    components: tuple[AlarmToolComponentReference, ...]


# Snapshot liviano consumible por el configurador de alarmas.
# catalog_revision permite conocer exactamente qué consolidado produjo las opciones mostradas.
@dataclass(frozen=True, slots=True)
class AlarmToolReferenceCatalog:
    catalog_revision: str
    tools: tuple[AlarmToolReference, ...]

    # Búsqueda tolerante para authoring: una key desconocida no convierte el catálogo en inválido.
    def get_tool(self, tool_key: str) -> AlarmToolReference | None:
        for tool in self.tools:
            if tool.tool_key == tool_key:
                return tool
        return None

    # Devuelve opciones de componentes o una colección vacía si la Tool no está disponible.
    def components(self, tool_key: str) -> tuple[AlarmToolComponentReference, ...]:
        tool = self.get_tool(tool_key)
        return () if tool is None else tool.components

    # Devuelve los subcomponentes visibles desde un componente concreto.
    def subcomponents(
        self,
        tool_key: str,
        component_key: str,
    ) -> tuple[AlarmToolSubcomponentReference, ...]:
        for component in self.components(tool_key):
            if component.component_key == component_key:
                return component.subcomponents
        return ()


# Reader con dependencia explícita del ToolCatalogStore.
# La ausencia del blob CURRENT es un estado legítimo y se representa como None.
# Los errores físicos del store no se capturan aquí para no confundir indisponibilidad con ausencia.
class AlarmToolReferenceReader:
    def __init__(self, *, store: ToolCatalogStore) -> None:
        if not isinstance(store, ToolCatalogStore):
            raise TypeError('store must be ToolCatalogStore')
        self._store = store

    def load(self) -> AlarmToolReferenceCatalog | None:
        snapshot = self._store.get_current()
        if snapshot is None:
            return None
        return AlarmToolReferenceCatalog(
            catalog_revision=snapshot.revision,
            tools=tuple(
                _reference_from_entry(entry)
                for entry in snapshot.tools
                # ToolStructure declara explícitamente que Strategic no tiene proyección de alarmas.
                # Se omite sólo de las sugerencias; Alarm Configuration continúa aceptando keys manuales.
                if entry.kind is not ToolConfigurationKind.STRATEGIC
            ),
        )


# Traduce una entrada del catálogo reutilizando las operaciones de alarmas de ToolStructure.
# Esto evita duplicar reglas de visibilidad y linked subcomponents dentro de Command Center Web.
def _reference_from_entry(entry: ToolCatalogEntry) -> AlarmToolReference:
    structure = entry.structure
    components: list[AlarmToolComponentReference] = []
    for component_key in structure.alarm_baseline_component_keys:
        component = structure.component(component_key)
        subcomponents: list[AlarmToolSubcomponentReference] = []
        for address in structure.alarm_subcomponent_addresses_for_component(component_key):
            owner = structure.component(address.owner_component_key)
            subcomponent = owner.subcomponent(address.subcomponent_key)
            subcomponents.append(
                AlarmToolSubcomponentReference(
                    owner_component_key=address.owner_component_key,
                    subcomponent_key=address.subcomponent_key,
                    display_name=subcomponent.display_name,
                )
            )
        components.append(
            AlarmToolComponentReference(
                component_key=component.key,
                display_name=component.display_name,
                subcomponents=tuple(subcomponents),
            )
        )
    return AlarmToolReference(
        tool_key=entry.tool_key,
        display_name=entry.display_name,
        kind=entry.kind,
        source_release_id=entry.source_release_id,
        components=tuple(components),
    )
