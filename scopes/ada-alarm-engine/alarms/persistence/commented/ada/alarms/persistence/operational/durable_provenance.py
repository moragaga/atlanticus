# El contrato de lectura atribuye un artifact exacto a cada registro confirmado del WAL.
# Un commit V2 pertenece al artifact de destino aunque preceda al registro de adopción.
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ada.alarms.persistence.operational.configuration_adoption import (
    AlarmArtifactRefSnapshot,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
)
from ada.alarms.persistence.operational.errors import AlarmPersistenceCorruptionError
from ada.alarms.persistence.operational.models import EngineCommitRecord, JournalEntry


@dataclass(frozen=True, slots=True)
class AttributedDurableEntry:
    entry: JournalEntry
    artifact_ref: AlarmArtifactRefSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.entry, JournalEntry):
            raise TypeError('entry must be a JournalEntry')
        if not isinstance(self.artifact_ref, AlarmArtifactRefSnapshot):
            raise TypeError('artifact_ref must be an AlarmArtifactRefSnapshot')


# El helper recibe entradas ya validadas en su conjunto por EngineJournal.
# Primero relaciona cada grupo V2 con la adopción que lo confirma al final del batch.
def attribute_durable_entries(
    entries: Sequence[JournalEntry],
) -> tuple[AttributedDurableEntry, ...]:
    targets: dict[int, AlarmArtifactRefSnapshot] = {}
    for index, entry in enumerate(entries):
        adoption = entry.record
        if not isinstance(adoption, ConfigurationAdoptionRecordV2):
            continue
        first = index - len(adoption.group_commits)
        if first < 0:
            raise AlarmPersistenceCorruptionError('V2 adoption has missing group commits')
        for offset, reference in enumerate(adoption.group_commits):
            at = first + offset
            group_record = entries[at].record
            if (
                at in targets
                or not isinstance(group_record, EngineCommitRecord)
                or group_record.commit.priority_group != reference.priority_group
                or group_record.commit.commit_id != reference.commit_id
                or group_record.record_hash != reference.record_hash
            ):
                raise AlarmPersistenceCorruptionError('V2 adoption group provenance is invalid')
            targets[at] = adoption.target_artifact_ref

    # Los commits ordinarios heredan EFFECTIVE; los commits ligados a V2 usan el target.
    current: AlarmArtifactRefSnapshot | None = None
    attributed: list[AttributedDurableEntry] = []
    for index, entry in enumerate(entries):
        record = entry.record
        if isinstance(record, ConfigurationAdoptionRecord):
            if current != record.previous_artifact_ref:
                raise AlarmPersistenceCorruptionError('durable artifact chain is inconsistent')
            current = record.target_artifact_ref
            attributed.append(AttributedDurableEntry(entry=entry, artifact_ref=current))
            continue
        if not isinstance(record, EngineCommitRecord):
            raise AlarmPersistenceCorruptionError('durable entry has unsupported record type')
        reference = targets.get(index, current)
        if reference is None:
            raise AlarmPersistenceCorruptionError('group commit has no confirmed artifact origin')
        if (
            record.commit.alarm_configuration_revision != reference.alarm_configuration_revision
            or record.commit.tool_registry_revision != reference.confirmed_tool_catalog_revision
        ):
            raise AlarmPersistenceCorruptionError('group commit differs from its artifact origin')
        attributed.append(AttributedDurableEntry(entry=entry, artifact_ref=reference))
    return tuple(attributed)
