from __future__ import annotations

# Este módulo modela la topología lógica de una Tool y las proyecciones derivadas que consumen KPI, alarmas y composición.
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada.configuration.tools.enums import (
    ProcessLayoutRole,
    ToolConfigurationKind,
    ToolScope,
)
from ada.configuration.tools.errors import ToolConfigurationValidationError
from ada.configuration.tools.validation import require_display_name, require_key

_SYSTEM_KPI_DESTINATION_KEYS = ('global_indicators', 'time_status')
_RESERVED_COMPONENT_KEYS = frozenset(_SYSTEM_KPI_DESTINATION_KEYS)


@dataclass(frozen=True, slots=True)
class ToolSubcomponent:
    key: str
    display_name: str
    linked_component_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        key = require_key(self.key, label='Tool subcomponent key')
        display_name = require_display_name(
            self.display_name,
            label='Tool subcomponent display name',
        )
        linked_component_keys = tuple(
            require_key(value, label='Tool linked component key')
            for value in self.linked_component_keys
        )
        if len(linked_component_keys) != len(set(linked_component_keys)):
            raise ToolConfigurationValidationError(
                'Tool subcomponent linked component keys must be unique'
            )
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'linked_component_keys', linked_component_keys)

    def to_document(self) -> dict[str, object]:
        return {
            'key': self.key,
            'display_name': self.display_name,
            'linked_component_keys': list(self.linked_component_keys),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ToolSubcomponent:
        try:
            raw_links = document.get('linked_component_keys', [])
            if not isinstance(raw_links, list):
                raise TypeError
            return cls(
                key=document['key'],
                display_name=document['display_name'],
                linked_component_keys=tuple(raw_links),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ToolConfigurationValidationError):
                raise
            raise ToolConfigurationValidationError(
                'Tool subcomponent contract is invalid'
            ) from error


@dataclass(frozen=True, slots=True)
class ToolComponent:
    key: str
    display_name: str
    subcomponents: tuple[ToolSubcomponent, ...] = ()
    scope: ToolScope | None = None
    layout_role: ProcessLayoutRole | None = None

    def __post_init__(self) -> None:
        key = require_key(self.key, label='Tool component key')
        display_name = require_display_name(
            self.display_name,
            label='Tool component display name',
        )
        subcomponents = tuple(self.subcomponents)
        if any(not isinstance(item, ToolSubcomponent) for item in subcomponents):
            raise ToolConfigurationValidationError(
                'Tool component subcomponents must contain ToolSubcomponent values'
            )
        subcomponent_keys = tuple(item.key for item in subcomponents)
        if len(subcomponent_keys) != len(set(subcomponent_keys)):
            raise ToolConfigurationValidationError(
                f'Tool component {key!r} contains duplicate subcomponent keys'
            )
        if self.scope is not None and not isinstance(self.scope, ToolScope):
            raise ToolConfigurationValidationError('Tool component scope is invalid')
        if self.layout_role is not None and not isinstance(
            self.layout_role,
            ProcessLayoutRole,
        ):
            raise ToolConfigurationValidationError('Tool component layout role is invalid')
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'subcomponents', subcomponents)

    def subcomponent(self, key: str) -> ToolSubcomponent:
        normalized = require_key(key, label='Tool subcomponent key')
        for subcomponent in self.subcomponents:
            if subcomponent.key == normalized:
                return subcomponent
        raise ToolConfigurationValidationError(
            f'Unknown Tool subcomponent for component {self.key!r}: {normalized!r}'
        )

    def to_document(self) -> dict[str, object]:
        return {
            'key': self.key,
            'display_name': self.display_name,
            'scope': self.scope.value if self.scope is not None else None,
            'layout_role': self.layout_role.value if self.layout_role is not None else None,
            'subcomponents': [item.to_document() for item in self.subcomponents],
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ToolComponent:
        try:
            raw_subcomponents = document.get('subcomponents', [])
            if not isinstance(raw_subcomponents, list):
                raise TypeError
            if not all(isinstance(item, Mapping) for item in raw_subcomponents):
                raise TypeError
            raw_scope = document.get('scope')
            raw_layout_role = document.get('layout_role')
            return cls(
                key=document['key'],
                display_name=document['display_name'],
                subcomponents=tuple(
                    ToolSubcomponent.from_document(item) for item in raw_subcomponents
                ),
                scope=ToolScope(raw_scope) if raw_scope is not None else None,
                layout_role=(
                    ProcessLayoutRole(raw_layout_role)
                    if raw_layout_role is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ToolConfigurationValidationError):
                raise
            raise ToolConfigurationValidationError(
                'Tool component contract is invalid'
            ) from error


@dataclass(frozen=True, slots=True)
class ToolSubcomponentAddress:
    owner_component_key: str
    subcomponent_key: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'owner_component_key',
            require_key(self.owner_component_key, label='Tool component key'),
        )
        object.__setattr__(
            self,
            'subcomponent_key',
            require_key(self.subcomponent_key, label='Tool subcomponent key'),
        )


@dataclass(frozen=True, slots=True)
class ToolStructure:
    tool_key: str
    kind: ToolConfigurationKind
    components: tuple[ToolComponent, ...]
    operational_scope: ToolScope | None = None

    def __post_init__(self) -> None:
        tool_key = require_key(self.tool_key, label='Tool Structure tool key')
        if not isinstance(self.kind, ToolConfigurationKind):
            raise ToolConfigurationValidationError('Tool Structure kind is invalid')
        components = tuple(self.components)
        if not components:
            raise ToolConfigurationValidationError('Tool Structure requires components')
        if any(not isinstance(item, ToolComponent) for item in components):
            raise ToolConfigurationValidationError(
                'Tool Structure components must contain ToolComponent values'
            )
        component_keys = tuple(item.key for item in components)
        if len(component_keys) != len(set(component_keys)):
            raise ToolConfigurationValidationError(
                'Tool Structure contains duplicate component keys'
            )
        reserved_key = next(
            (key for key in component_keys if key in _RESERVED_COMPONENT_KEYS),
            None,
        )
        if reserved_key is not None:
            raise ToolConfigurationValidationError(
                f'Tool Structure component key is reserved: {reserved_key!r}'
            )
        if self.operational_scope is not None and not isinstance(
            self.operational_scope,
            ToolScope,
        ):
            raise ToolConfigurationValidationError(
                'Tool Structure operational scope is invalid'
            )
        object.__setattr__(self, 'tool_key', tool_key)
        object.__setattr__(self, 'components', components)
        _validate_linked_component_keys(self)
        _validate_visible_subcomponent_namespaces(self)

        # PROCESS e INTEGRATED_OPERATIONS conservan sus validaciones conocidas.
        if self.kind is ToolConfigurationKind.PROCESS:
            _validate_process_structure(self)
        elif self.kind is ToolConfigurationKind.INTEGRATED_OPERATIONS:
            _validate_integrated_operations_structure(self)
        # STRATEGIC sólo usa las invariantes estructurales comunes.
        # Su forma funcional todavía no está definida y no se inventa aquí.

    @property
    def kpi_destination_keys(self) -> tuple[str, ...]:
        return (*_SYSTEM_KPI_DESTINATION_KEYS, *(item.key for item in self.components))

    @property
    def alarm_baseline_component_keys(self) -> tuple[str, ...]:
        # Tools expone el kind, pero no inventa una proyección de alarmas para Strategic.
        if self.kind is ToolConfigurationKind.STRATEGIC:
            raise ToolConfigurationValidationError(
                'Alarm projection is not defined for Strategic Tool Structure'
            )
        if self.kind is ToolConfigurationKind.PROCESS:
            return (self.component_for_layout_role(ProcessLayoutRole.CENTER).key,)
        return tuple(component.key for component in self.components)

    @property
    def alarm_subcomponent_addresses(self) -> tuple[ToolSubcomponentAddress, ...]:
        # El consumidor de alarmas debe resolver la semántica de Strategic usando kind.
        if self.kind is ToolConfigurationKind.STRATEGIC:
            raise ToolConfigurationValidationError(
                'Alarm projection is not defined for Strategic Tool Structure'
            )
        if self.kind is ToolConfigurationKind.PROCESS:
            center = self.component_for_layout_role(ProcessLayoutRole.CENTER)
            return tuple(
                ToolSubcomponentAddress(center.key, item.key)
                for item in center.subcomponents
            )
        return tuple(
            ToolSubcomponentAddress(component.key, subcomponent.key)
            for component in self.components
            for subcomponent in component.subcomponents
        )

    def component(self, key: str) -> ToolComponent:
        normalized = require_key(key, label='Tool component key')
        for component in self.components:
            if component.key == normalized:
                return component
        raise ToolConfigurationValidationError(
            f'Unknown Tool component: {normalized!r}'
        )

    def component_for_layout_role(self, role: ProcessLayoutRole) -> ToolComponent:
        if not isinstance(role, ProcessLayoutRole):
            raise ToolConfigurationValidationError('Process layout role is invalid')
        for component in self.components:
            if component.layout_role is role:
                return component
        raise ToolConfigurationValidationError(
            f'Unknown Process layout role: {role.value!r}'
        )

    def subcomponent_address(
        self,
        *,
        component_key: str,
        subcomponent_key: str,
    ) -> ToolSubcomponentAddress:
        component = self.component(component_key)
        normalized = require_key(subcomponent_key, label='Tool subcomponent key')
        for subcomponent in component.subcomponents:
            if subcomponent.key == normalized:
                return ToolSubcomponentAddress(component.key, subcomponent.key)
        for owner in self.components:
            for subcomponent in owner.subcomponents:
                if (
                    subcomponent.key == normalized
                    and component.key in subcomponent.linked_component_keys
                ):
                    return ToolSubcomponentAddress(owner.key, subcomponent.key)
        raise ToolConfigurationValidationError(
            'Unknown Tool subcomponent for component '
            f'{component.key!r}: {normalized!r}'
        )

    def alarm_subcomponent_addresses_for_component(
        self,
        component_key: str,
    ) -> tuple[ToolSubcomponentAddress, ...]:
        # No se reutiliza por defecto el comportamiento de Operaciones Integradas para Strategic.
        if self.kind is ToolConfigurationKind.STRATEGIC:
            raise ToolConfigurationValidationError(
                'Alarm projection is not defined for Strategic Tool Structure'
            )
        component = self.component(component_key)
        if self.kind is ToolConfigurationKind.PROCESS:
            center = self.component_for_layout_role(ProcessLayoutRole.CENTER)
            if component.key != center.key:
                return ()
        direct = tuple(
            ToolSubcomponentAddress(component.key, item.key)
            for item in component.subcomponents
        )
        if self.kind is ToolConfigurationKind.PROCESS:
            return direct
        linked = tuple(
            ToolSubcomponentAddress(owner.key, subcomponent.key)
            for owner in self.components
            for subcomponent in owner.subcomponents
            if component.key in subcomponent.linked_component_keys
        )
        return (*direct, *linked)

    def to_document(self) -> dict[str, object]:
        return {
            'tool_key': self.tool_key,
            'kind': self.kind.value,
            'operational_scope': (
                self.operational_scope.value if self.operational_scope is not None else None
            ),
            'components': [component.to_document() for component in self.components],
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ToolStructure:
        try:
            raw_components = document['components']
            if not isinstance(raw_components, list):
                raise TypeError
            if not all(isinstance(item, Mapping) for item in raw_components):
                raise TypeError
            raw_scope = document.get('operational_scope')
            return cls(
                tool_key=document['tool_key'],
                kind=ToolConfigurationKind(document['kind']),
                components=tuple(
                    ToolComponent.from_document(item) for item in raw_components
                ),
                operational_scope=(
                    ToolScope(raw_scope) if raw_scope is not None else None
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ToolConfigurationValidationError):
                raise
            raise ToolConfigurationValidationError(
                'Tool Structure contract is invalid'
            ) from error


def _validate_linked_component_keys(structure: ToolStructure) -> None:
    components = {component.key: component for component in structure.components}
    for owner in structure.components:
        for subcomponent in owner.subcomponents:
            for linked_key in subcomponent.linked_component_keys:
                if linked_key == owner.key:
                    raise ToolConfigurationValidationError(
                        'Tool subcomponent must not link to its owner component'
                    )
                linked_component = components.get(linked_key)
                if linked_component is None:
                    raise ToolConfigurationValidationError(
                        f'Unknown linked Tool component: {linked_key!r}'
                    )
                if (
                    owner.scope is not None
                    and linked_component.scope is not None
                    and owner.scope is not linked_component.scope
                ):
                    raise ToolConfigurationValidationError(
                        'Tool subcomponent linked components must share scope'
                    )


def _validate_visible_subcomponent_namespaces(structure: ToolStructure) -> None:
    for component in structure.components:
        visible: set[str] = set()
        for owner in structure.components:
            for subcomponent in owner.subcomponents:
                if owner.key != component.key and component.key not in (
                    subcomponent.linked_component_keys
                ):
                    continue
                if subcomponent.key in visible:
                    raise ToolConfigurationValidationError(
                        'Tool component has ambiguous visible subcomponent key: '
                        f'{component.key!r}/{subcomponent.key!r}'
                    )
                visible.add(subcomponent.key)


def _validate_process_structure(structure: ToolStructure) -> None:
    if structure.operational_scope is None:
        raise ToolConfigurationValidationError(
            'Process Tool Structure requires operational scope'
        )
    roles: list[ProcessLayoutRole] = []
    for component in structure.components:
        if component.scope is not None:
            raise ToolConfigurationValidationError(
                'Process Tool components inherit operational scope and must not declare scope'
            )
        if component.layout_role is None:
            raise ToolConfigurationValidationError(
                f'Process Tool component {component.key!r} requires layout role'
            )
        if any(item.linked_component_keys for item in component.subcomponents):
            raise ToolConfigurationValidationError(
                'Process Tool subcomponents must not declare linked component keys'
            )
        roles.append(component.layout_role)
    if len(roles) != len(set(roles)):
        raise ToolConfigurationValidationError(
            'Process Tool Structure contains duplicate layout roles'
        )
    if ProcessLayoutRole.CENTER not in roles:
        raise ToolConfigurationValidationError(
            'Process Tool Structure requires CENTER layout role'
        )
    center = structure.component_for_layout_role(ProcessLayoutRole.CENTER)
    if not center.subcomponents:
        raise ToolConfigurationValidationError(
            'Process CENTER component requires at least one subcomponent'
        )


def _validate_integrated_operations_structure(structure: ToolStructure) -> None:
    if structure.operational_scope is not None:
        raise ToolConfigurationValidationError(
            'Integrated Operations Tool Structure must not declare operational scope'
        )
    for component in structure.components:
        if component.scope is None:
            raise ToolConfigurationValidationError(
                f'Integrated Operations component {component.key!r} requires scope'
            )
        if component.layout_role is not None:
            raise ToolConfigurationValidationError(
                'Integrated Operations components must not declare Process layout roles'
            )
        if not component.subcomponents:
            raise ToolConfigurationValidationError(
                f'Integrated Operations component {component.key!r} requires subcomponents'
            )
