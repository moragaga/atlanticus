# Contratos inmutables de catálogo y asignaciones ADA; ningún campo se incorpora a Atlanticus Users.
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ada.web.operational.identification.errors import (
    OperationalIdentificationError,
    OperationalReferenceError,
)

_USER_ID = re.compile(r'^user:[0-9a-f]{24}$')
_POSITION_ID = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
_AREAS = (('mina', 'Mina'), ('planta', 'Planta'))
_GROUPS = ((1, 'Grupo 1'), (2, 'Grupo 2'), (3, 'Grupo 3'), (4, 'Grupo 4'))


# Se respeta la identidad canónica producida actualmente por Atlanticus Users.
def validate_user_id(user_id: str) -> str:
    if not isinstance(user_id, str) or not _USER_ID.fullmatch(user_id):
        raise OperationalIdentificationError('Operational user id is invalid')
    return user_id


@dataclass(frozen=True, slots=True)
# Un cargo conserva un identificador estable aunque cambie su nombre visible.
class Position:
    id: str
    label: str
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _POSITION_ID.fullmatch(self.id):
            raise OperationalIdentificationError('Position id is invalid')
        if (
            not isinstance(self.label, str)
            or not self.label.strip()
            or self.label != self.label.strip()
        ):
            raise OperationalIdentificationError('Position label is invalid')
        if len(self.label) > 120 or any(ord(char) < 32 for char in self.label):
            raise OperationalIdentificationError('Position label is invalid')
        if type(self.active) is not bool:
            raise OperationalIdentificationError('Position active flag must be boolean')

    def to_document(self) -> dict[str, object]:
        return {'id': self.id, 'label': self.label, 'active': self.active}

    @classmethod
    def from_document(cls, item: object) -> Position:
        if not isinstance(item, dict) or set(item) != {'id', 'label', 'active'}:
            raise OperationalIdentificationError('Position document is invalid')
        return cls(id=item['id'], label=item['label'], active=item['active'])


@dataclass(frozen=True, slots=True)
# Áreas y grupos son cerrados en V1; los cargos se administran con identidad estable.
class OperationalCatalog:
    positions: tuple[Position, ...] = ()

    def __post_init__(self) -> None:
        positions = tuple(self.positions)
        if not all(isinstance(position, Position) for position in positions):
            raise OperationalIdentificationError('Catalog positions must be Position entries')
        ids = tuple(position.id for position in positions)
        labels = tuple(position.label.casefold() for position in positions)
        if len(ids) != len(set(ids)) or len(labels) != len(set(labels)):
            raise OperationalIdentificationError('Catalog positions must be unique')
        object.__setattr__(self, 'positions', tuple(sorted(positions, key=lambda item: item.id)))

    def position(self, position_id: str) -> Position | None:
        return next((item for item in self.positions if item.id == position_id), None)

    # Un cargo desactivado no admite asignaciones nuevas, pero puede conservarse en una existente.
    def require_position(self, position_id: str, *, current_id: str | None = None) -> None:
        position = self.position(position_id)
        if position is None or (not position.active and current_id != position_id):
            raise OperationalReferenceError('Position is unavailable for new assignment')

    # Se conservan los cargos antiguos para no dejar referencias huérfanas.
    def validate_revision(self, previous: OperationalCatalog) -> None:
        existing = {item.id for item in previous.positions}
        proposed = {item.id for item in self.positions}
        if not existing.issubset(proposed):
            raise OperationalReferenceError('Previously defined positions must be retained')

    def to_document(self) -> dict[str, object]:
        return {
            'areas': [{'id': key, 'label': label} for key, label in _AREAS],
            'groups': [{'id': key, 'label': label} for key, label in _GROUPS],
            'positions': [item.to_document() for item in self.positions],
        }

    @classmethod
    def from_document(cls, value: object) -> OperationalCatalog:
        if not isinstance(value, dict) or set(value) != {'areas', 'groups', 'positions'}:
            raise OperationalIdentificationError('Operational catalog document is invalid')
        if value['areas'] != [{'id': key, 'label': label} for key, label in _AREAS]:
            raise OperationalIdentificationError('Operational areas contract is invalid')
        if value['groups'] != [{'id': key, 'label': label} for key, label in _GROUPS]:
            raise OperationalIdentificationError('Operational groups contract is invalid')
        if not isinstance(value['positions'], list):
            raise OperationalIdentificationError('Operational positions contract is invalid')
        return cls(positions=tuple(Position.from_document(item) for item in value['positions']))


@dataclass(frozen=True, slots=True)
# Los tres datos son opcionales y pertenecen al usuario, nunca al perfil.
class OperationalAssignment:
    user_id: str
    area_id: str | None = None
    position_id: str | None = None
    group_id: int | None = None

    def __post_init__(self) -> None:
        validate_user_id(self.user_id)
        if self.area_id is not None and (
            not isinstance(self.area_id, str) or self.area_id not in {key for key, _ in _AREAS}
        ):
            raise OperationalIdentificationError('Operational area id is invalid')
        if self.position_id is not None and (
            not isinstance(self.position_id, str) or not _POSITION_ID.fullmatch(self.position_id)
        ):
            raise OperationalIdentificationError('Operational position id is invalid')
        if self.group_id is not None and (
            type(self.group_id) is not int or self.group_id not in {key for key, _ in _GROUPS}
        ):
            raise OperationalIdentificationError('Operational group id is invalid')

    def to_document(self) -> dict[str, object]:
        return {
            'user_id': self.user_id,
            'area_id': self.area_id,
            'position_id': self.position_id,
            'group_id': self.group_id,
        }

    @classmethod
    def from_document(cls, value: object) -> OperationalAssignment:
        if not isinstance(value, dict) or set(value) != {
            'user_id',
            'area_id',
            'position_id',
            'group_id',
        }:
            raise OperationalIdentificationError('Operational assignment document is invalid')
        return cls(**value)


OperationalDocument = OperationalCatalog | OperationalAssignment


# El tipo se decide por la identidad de la Source, sin lectores legacy.
def parse_document(kind: str, value: dict[str, Any]) -> OperationalDocument:
    if kind == 'catalog':
        return OperationalCatalog.from_document(value)
    if kind == 'assignment':
        return OperationalAssignment.from_document(value)
    raise OperationalIdentificationError('Operational document kind is invalid')
