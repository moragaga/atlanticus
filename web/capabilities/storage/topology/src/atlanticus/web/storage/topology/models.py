from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, TypeVar

from atlanticus.web.storage.topology.errors import StorageTopologyConfigurationError

TTopology = TypeVar('TTopology')


class StorageResourceOverrideField(StrEnum):
    CONNECTION_REF = 'connection_ref'
    PHYSICAL_NAME = 'physical_name'


@dataclass(frozen=True, slots=True)
class StorageResourceContract(Generic[TTopology]):
    logical_id: str
    owner: str
    provider: str
    default_connection_ref: str | None
    default_physical_name: str
    topology: TTopology
    allowed_overrides: frozenset[StorageResourceOverrideField] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'logical_id', _require_text(self.logical_id, 'logical_id'))
        object.__setattr__(self, 'owner', _require_text(self.owner, 'owner'))
        object.__setattr__(self, 'provider', _require_text(self.provider, 'provider'))
        if self.default_connection_ref is not None:
            object.__setattr__(
                self,
                'default_connection_ref',
                _require_text(self.default_connection_ref, 'default_connection_ref'),
            )
        object.__setattr__(
            self,
            'default_physical_name',
            _require_text(self.default_physical_name, 'default_physical_name'),
        )
        if self.topology is None:
            raise StorageTopologyConfigurationError('topology must not be None')
        try:
            allowed_overrides = frozenset(self.allowed_overrides)
        except TypeError:
            raise StorageTopologyConfigurationError(
                'allowed_overrides must be an iterable of StorageResourceOverrideField values'
            ) from None
        if any(not isinstance(field, StorageResourceOverrideField) for field in allowed_overrides):
            raise StorageTopologyConfigurationError(
                'allowed_overrides must contain StorageResourceOverrideField values'
            )
        object.__setattr__(self, 'allowed_overrides', allowed_overrides)


@dataclass(frozen=True, slots=True)
class StorageResourceOverride:
    logical_id: str
    connection_ref: str | None = None
    physical_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'logical_id', _require_text(self.logical_id, 'logical_id'))
        if self.connection_ref is not None:
            object.__setattr__(
                self,
                'connection_ref',
                _require_text(self.connection_ref, 'connection_ref'),
            )
        if self.physical_name is not None:
            object.__setattr__(
                self,
                'physical_name',
                _require_text(self.physical_name, 'physical_name'),
            )
        if self.connection_ref is None and self.physical_name is None:
            raise StorageTopologyConfigurationError(
                'storage resource override must set connection_ref or physical_name'
            )


@dataclass(frozen=True, slots=True)
class ResolvedStorageResource(Generic[TTopology]):
    logical_id: str
    owner: str
    provider: str
    connection_ref: str
    physical_name: str
    topology: TTopology

    def __post_init__(self) -> None:
        object.__setattr__(self, 'logical_id', _require_text(self.logical_id, 'logical_id'))
        object.__setattr__(self, 'owner', _require_text(self.owner, 'owner'))
        object.__setattr__(self, 'provider', _require_text(self.provider, 'provider'))
        object.__setattr__(
            self,
            'connection_ref',
            _require_text(self.connection_ref, 'connection_ref'),
        )
        object.__setattr__(
            self,
            'physical_name',
            _require_text(self.physical_name, 'physical_name'),
        )
        if self.topology is None:
            raise StorageTopologyConfigurationError('topology must not be None')


@dataclass(frozen=True, slots=True)
class ResolvedStoragePlan:
    resources: tuple[ResolvedStorageResource[Any], ...]

    def __post_init__(self) -> None:
        try:
            resources = tuple(self.resources)
        except TypeError:
            raise StorageTopologyConfigurationError(
                'resources must be an iterable of ResolvedStorageResource values'
            ) from None
        if any(not isinstance(resource, ResolvedStorageResource) for resource in resources):
            raise StorageTopologyConfigurationError(
                'resources must contain ResolvedStorageResource values'
            )
        object.__setattr__(self, 'resources', resources)


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or not value.strip():
        raise StorageTopologyConfigurationError(f'{field_name} must be non-empty text')
    if value != value.strip():
        raise StorageTopologyConfigurationError(
            f'{field_name} must not contain surrounding whitespace'
        )
    if '\x00' in value:
        raise StorageTopologyConfigurationError(f'{field_name} must not contain null characters')
    return value
