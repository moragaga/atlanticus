from __future__ import annotations

from dataclasses import dataclass

from ada.configuration.tools import (
    ProcessLayoutRole,
    ToolConfigurationKind,
    ToolScope,
)
from ada.web.body.projection.errors import ToolBodyProjectionError


def _require_identity(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolBodyProjectionError(f'{label} is required')
    return value.strip().casefold()


def _component_wrapper_id(tool_key: str, component_key: str) -> str:
    return f'ada-tool-{tool_key}-component-{component_key}'


def _subcomponent_wrapper_id(
    tool_key: str,
    owner_component_key: str,
    subcomponent_key: str,
) -> str:
    return f'ada-tool-{tool_key}-subcomponent-{owner_component_key}-{subcomponent_key}'


@dataclass(frozen=True, slots=True)
class ToolBodySubcomponentBinding:
    tool_key: str
    owner_component_key: str
    subcomponent_key: str
    display_name: str
    linked_component_keys: tuple[str, ...]
    wrapper_id: str

    def __post_init__(self) -> None:
        tool_key = _require_identity(self.tool_key, label='Tool body tool key')
        owner_component_key = _require_identity(
            self.owner_component_key,
            label='Tool body owner component key',
        )
        subcomponent_key = _require_identity(
            self.subcomponent_key,
            label='Tool body subcomponent key',
        )
        display_name = self.display_name.strip()
        if not display_name:
            raise ToolBodyProjectionError('Tool body subcomponent display name is required')
        linked_component_keys = tuple(
            _require_identity(value, label='Tool body linked component key')
            for value in self.linked_component_keys
        )
        if len(linked_component_keys) != len(set(linked_component_keys)):
            raise ToolBodyProjectionError('Tool body linked component keys must be unique')
        expected_wrapper_id = _subcomponent_wrapper_id(
            tool_key,
            owner_component_key,
            subcomponent_key,
        )
        if self.wrapper_id != expected_wrapper_id:
            raise ToolBodyProjectionError(
                f'Tool body subcomponent wrapper id is invalid for {subcomponent_key!r}'
            )
        object.__setattr__(self, 'tool_key', tool_key)
        object.__setattr__(self, 'owner_component_key', owner_component_key)
        object.__setattr__(self, 'subcomponent_key', subcomponent_key)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'linked_component_keys', linked_component_keys)

    @property
    def visible_component_keys(self) -> tuple[str, ...]:
        return (self.owner_component_key, *self.linked_component_keys)

    def to_document(self) -> dict[str, object]:
        return {
            'tool_key': self.tool_key,
            'owner_component_key': self.owner_component_key,
            'subcomponent_key': self.subcomponent_key,
            'display_name': self.display_name,
            'linked_component_keys': list(self.linked_component_keys),
            'wrapper_id': self.wrapper_id,
        }


@dataclass(frozen=True, slots=True)
class ToolBodyComponentBinding:
    tool_key: str
    component_key: str
    display_name: str
    scope: ToolScope
    layout_role: ProcessLayoutRole | None
    wrapper_id: str
    subcomponents: tuple[ToolBodySubcomponentBinding, ...]

    def __post_init__(self) -> None:
        tool_key = _require_identity(self.tool_key, label='Tool body tool key')
        component_key = _require_identity(
            self.component_key,
            label='Tool body component key',
        )
        display_name = self.display_name.strip()
        if not display_name:
            raise ToolBodyProjectionError('Tool body component display name is required')
        if not isinstance(self.scope, ToolScope):
            raise ToolBodyProjectionError('Tool body component scope is invalid')
        if self.layout_role is not None and not isinstance(
            self.layout_role,
            ProcessLayoutRole,
        ):
            raise ToolBodyProjectionError('Tool body layout role is invalid')
        expected_wrapper_id = _component_wrapper_id(tool_key, component_key)
        if self.wrapper_id != expected_wrapper_id:
            raise ToolBodyProjectionError(
                f'Tool body component wrapper id is invalid for {component_key!r}'
            )
        subcomponents = tuple(self.subcomponents)
        if any(not isinstance(item, ToolBodySubcomponentBinding) for item in subcomponents):
            raise ToolBodyProjectionError(
                'Tool body component subcomponents contain invalid bindings'
            )
        if any(item.tool_key != tool_key for item in subcomponents):
            raise ToolBodyProjectionError(
                'Tool body subcomponent tool key must match component tool key'
            )
        if any(item.owner_component_key != component_key for item in subcomponents):
            raise ToolBodyProjectionError('Tool body subcomponent owner must match component key')
        subcomponent_keys = tuple(item.subcomponent_key for item in subcomponents)
        if len(subcomponent_keys) != len(set(subcomponent_keys)):
            raise ToolBodyProjectionError(
                f'Tool body component {component_key!r} contains duplicate subcomponents'
            )
        object.__setattr__(self, 'tool_key', tool_key)
        object.__setattr__(self, 'component_key', component_key)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'subcomponents', subcomponents)

    def to_document(self) -> dict[str, object]:
        return {
            'tool_key': self.tool_key,
            'component_key': self.component_key,
            'display_name': self.display_name,
            'scope': self.scope.value,
            'layout_role': self.layout_role.value if self.layout_role is not None else None,
            'wrapper_id': self.wrapper_id,
            'subcomponents': [item.to_document() for item in self.subcomponents],
        }


@dataclass(frozen=True, slots=True)
class ToolBodyProjection:
    tool_key: str
    kind: ToolConfigurationKind
    root_id: str
    components: tuple[ToolBodyComponentBinding, ...]

    def __post_init__(self) -> None:
        tool_key = _require_identity(self.tool_key, label='Tool body tool key')
        if not isinstance(self.kind, ToolConfigurationKind):
            raise ToolBodyProjectionError('Tool body kind is invalid')
        expected_root_id = f'ada-tool-{tool_key}-body'
        if self.root_id != expected_root_id:
            raise ToolBodyProjectionError('Tool body root id is invalid')
        components = tuple(self.components)
        if not components:
            raise ToolBodyProjectionError('Tool body projection requires components')
        if any(not isinstance(item, ToolBodyComponentBinding) for item in components):
            raise ToolBodyProjectionError('Tool body projection contains invalid components')
        if any(item.tool_key != tool_key for item in components):
            raise ToolBodyProjectionError(
                'Tool body component tool key must match projection tool key'
            )
        component_keys = tuple(item.component_key for item in components)
        if len(component_keys) != len(set(component_keys)):
            raise ToolBodyProjectionError('Tool body component keys must be unique')
        wrapper_ids = tuple(item.wrapper_id for item in components) + tuple(
            subcomponent.wrapper_id
            for component in components
            for subcomponent in component.subcomponents
        )
        if len(wrapper_ids) != len(set(wrapper_ids)):
            raise ToolBodyProjectionError('Tool body wrapper ids must be unique')
        object.__setattr__(self, 'tool_key', tool_key)
        object.__setattr__(self, 'components', components)

    @property
    def component_keys(self) -> tuple[str, ...]:
        return tuple(item.component_key for item in self.components)

    def component(self, component_key: str) -> ToolBodyComponentBinding:
        normalized = _require_identity(
            component_key,
            label='Tool body component key',
        )
        for component in self.components:
            if component.component_key == normalized:
                return component
        raise ToolBodyProjectionError(f'Unknown Tool body component: {normalized!r}')

    def component_for_layout_role(
        self,
        role: ProcessLayoutRole,
    ) -> ToolBodyComponentBinding:
        if self.kind is not ToolConfigurationKind.PROCESS:
            raise ToolBodyProjectionError(
                'Tool body layout roles are available only for Process Tools'
            )
        if not isinstance(role, ProcessLayoutRole):
            raise ToolBodyProjectionError('Tool body layout role is invalid')
        for component in self.components:
            if component.layout_role is role:
                return component
        raise ToolBodyProjectionError(f'Unknown Tool body layout role: {role.value!r}')

    def subcomponent(
        self,
        *,
        component_key: str,
        subcomponent_key: str,
    ) -> ToolBodySubcomponentBinding:
        component = self.component(component_key)
        normalized = _require_identity(
            subcomponent_key,
            label='Tool body subcomponent key',
        )
        for owner in self.components:
            for subcomponent in owner.subcomponents:
                if subcomponent.subcomponent_key != normalized:
                    continue
                if component.component_key in subcomponent.visible_component_keys:
                    return subcomponent
        raise ToolBodyProjectionError(
            'Unknown Tool body subcomponent for component '
            f'{component.component_key!r}: {normalized!r}'
        )

    def to_document(self) -> dict[str, object]:
        return {
            'tool_key': self.tool_key,
            'kind': self.kind.value,
            'root_id': self.root_id,
            'components': [item.to_document() for item in self.components],
        }
