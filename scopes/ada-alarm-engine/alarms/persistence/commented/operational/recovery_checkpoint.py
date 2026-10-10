from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_CHECKPOINT_VERSION = 'alarm-operational-recovery-checkpoint.v1'
_HASH = re.compile(r'[0-9a-f]{64}')


# SHA-256 canónico protege todos los campos serializados del checkpoint.
def _digest(document: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode(
            'utf-8'
        )
    ).hexdigest()


# Contiene dos representaciones: estado vigente íntegro y ancla física del WAL.
@dataclass(frozen=True, slots=True)
class RecoveryCheckpoint:
    sequence: int
    journal_head: dict[str, object]
    effective_head: dict[str, object] | None
    groups: tuple[dict[str, object], ...]
    wal_anchor_sha256: str
    sha256: str

    # Construir la firma después de ordenar grupos y fijar el head alineado.
    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        journal_head: dict[str, object],
        effective_head: dict[str, object] | None,
        groups: Sequence[dict[str, object]],
        wal_anchor_sha256: str,
    ) -> RecoveryCheckpoint:
        unsigned: dict[str, object] = {
            'schema_version': _CHECKPOINT_VERSION,
            'sequence': sequence,
            'journal_head': journal_head,
            'effective_head': effective_head,
            'groups': list(groups),
            'wal_anchor_sha256': wal_anchor_sha256,
        }
        return cls.from_document({**unsigned, 'sha256': _digest(unsigned)})

    def as_document(self) -> dict[str, object]:
        return {
            'schema_version': _CHECKPOINT_VERSION,
            'sequence': self.sequence,
            'journal_head': self.journal_head,
            'effective_head': self.effective_head,
            'groups': list(self.groups),
            'wal_anchor_sha256': self.wal_anchor_sha256,
            'sha256': self.sha256,
        }

    # Una representación parcial, alterada o ambigua se rechaza sin normalizarla.
    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> RecoveryCheckpoint:
        expected = {
            'schema_version',
            'sequence',
            'journal_head',
            'effective_head',
            'groups',
            'wal_anchor_sha256',
            'sha256',
        }
        if not isinstance(document, Mapping) or set(document) != expected:
            raise ValueError('recovery checkpoint fields are invalid')
        if document['schema_version'] != _CHECKPOINT_VERSION:
            raise ValueError('recovery checkpoint schema is unsupported')
        sequence = document['sequence']
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError('recovery checkpoint sequence is invalid')
        head = document['journal_head']
        if not isinstance(head, dict) or set(head) != {
            'journal_head_schema_version', 'durable', 'materialized'
        } or head['durable'] is None or head['durable'] != head['materialized']:
            raise ValueError('recovery checkpoint requires an aligned journal head')
        effective = document['effective_head']
        if not isinstance(effective, dict):
            raise ValueError('recovery checkpoint EFFECTIVE is invalid')
        groups = document['groups']
        if not isinstance(groups, list) or not all(isinstance(group, dict) for group in groups):
            raise ValueError('recovery checkpoint groups are invalid')
        keys = [group.get('priority_group') for group in groups]
        if not all(isinstance(key, str) and key for key in keys) or keys != sorted(set(keys)):
            raise ValueError('recovery checkpoint groups must be unique and sorted')
        anchor = document['wal_anchor_sha256']
        checksum = document['sha256']
        if (
            not isinstance(anchor, str)
            or _HASH.fullmatch(anchor) is None
            or not isinstance(checksum, str)
            or _HASH.fullmatch(checksum) is None
            or _digest({key: value for key, value in document.items() if key != 'sha256'})
            != checksum
        ):
            raise ValueError('recovery checkpoint integrity check failed')
        return cls(
            sequence=sequence,
            journal_head=head,
            effective_head=effective,
            groups=tuple(groups),
            wal_anchor_sha256=anchor,
            sha256=checksum,
        )


# Solo dos slots reutilizables: no existe una nueva generación física por ciclo.
def latest_checkpoint(documents: Sequence[object | None]) -> RecoveryCheckpoint | None:
    checkpoints = [
        item if isinstance(item, RecoveryCheckpoint) else RecoveryCheckpoint.from_document(item)
        for item in documents if item is not None
    ]
    if not checkpoints:
        return None
    if len(checkpoints) == 2 and checkpoints[0].sequence == checkpoints[1].sequence:
        raise ValueError('recovery checkpoint generations conflict')
    return max(checkpoints, key=lambda item: item.sequence)
