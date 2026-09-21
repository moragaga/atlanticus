from __future__ import annotations

from dataclasses import dataclass

from ada.web.tools.enums import ToolConfigurationKind
from ada_command_center.tools.catalog import ToolCatalogEntry, ToolCatalogStore
from atlanticus.web.source.models import SourceReleaseId


@dataclass(frozen=True, slots=True)
class AlarmToolSubcomponentReference:
    owner_component_key: str
    subcomponent_key: str
    display_name: str


@dataclass(frozen=True, slots=True)
class AlarmToolComponentReference:
    component_key: str
    display_name: str
    subcomponents: tuple[AlarmToolSubcomponentReference, ...]


@dataclass(frozen=True, slots=True)
class AlarmToolReference:
    tool_key: str
    display_name: str
    kind: ToolConfigurationKind
    source_release_id: SourceReleaseId
    components: tuple[AlarmToolComponentReference, ...]


@dataclass(frozen=True, slots=True)
class AlarmToolReferenceCatalog:
    catalog_revision: str
    tools: tuple[AlarmToolReference, ...]

    def get_tool(self, tool_key: str) -> AlarmToolReference | None:
        for tool in self.tools:
            if tool.tool_key == tool_key:
                return tool
        return None

    def components(self, tool_key: str) -> tuple[AlarmToolComponentReference, ...]:
        tool = self.get_tool(tool_key)
        return () if tool is None else tool.components

    def subcomponents(
        self,
        tool_key: str,
        component_key: str,
    ) -> tuple[AlarmToolSubcomponentReference, ...]:
        for component in self.components(tool_key):
            if component.component_key == component_key:
                return component.subcomponents
        return ()


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
                if entry.kind is not ToolConfigurationKind.STRATEGIC
            ),
        )


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
