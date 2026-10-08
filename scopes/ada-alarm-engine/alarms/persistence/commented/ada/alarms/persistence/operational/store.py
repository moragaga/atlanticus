# Espejo pedagógico del módulo operacional store.py.
# Mantiene la lógica y los contratos del archivo productivo correspondiente.
from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from pathlib import Path

from ada.alarms.persistence.operational.configuration_adoption import (
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    GroupCommitReference,
)
from ada.alarms.persistence.operational.effective_head import (
    AlarmEffectiveConfigurationHead,
)
from ada.alarms.persistence.operational.errors import (
    AlarmPersistenceConflictError,
    AlarmPersistenceCorruptionError,
    AlarmPersistenceValidationError,
    AlarmPersistenceWriteError,
    AlarmRecoveryRequiredError,
)
from ada.alarms.persistence.operational.journal import EngineJournal
from ada.alarms.persistence.operational.models import (
    CommitBatchResult,
    EngineCommitRecord,
    GroupRuntimeSnapshot,
    JournalEntry,
    JournalHead,
    JournalPosition,
    RecoveryResult,
    segment_id_for_evaluated_at,
)
from ada.alarms.persistence.operational.paths import AlarmPersistencePaths
from ada.alarms.persistence.operational.serialization import build_record_hash
from atlanticus.state import AtomicJsonStore, StateError

AuthorityCheck = Callable[[], None]
MutationFence = Callable[[], AbstractContextManager[None]]


# Coordina el WAL, las cabezas durables y los snapshots con autoridad de escritura.
class AlarmPersistence:
    def __init__(
        self,
        *,
        shared_volume_path: str | Path,
        max_state_document_bytes: int | None = None,
    ) -> None:
        self._paths = AlarmPersistencePaths(shared_volume_path=shared_volume_path)
        self._state = AtomicJsonStore(
            root_path=self._paths.alarms_root,
            max_document_bytes=max_state_document_bytes,
        )
        self._journal = EngineJournal(paths=self._paths)
        self._write_lock = threading.RLock()

    @property
    def paths(self) -> AlarmPersistencePaths:
        return self._paths

    def read_head(self) -> JournalHead:
        try:
            document = self._state.read(self._paths.journal_head_relative)
        except StateError as error:
            raise AlarmPersistenceCorruptionError(
                'could not read Alarm Engine journal head'
            ) from error
        if document is None:
            return JournalHead()
        return JournalHead.from_document(document)

    def read_snapshot(self, priority_group: str) -> GroupRuntimeSnapshot | None:
        try:
            document = self._state.read(self._paths.group_snapshot_relative(priority_group))
        except StateError as error:
            raise AlarmPersistenceCorruptionError(
                f'could not read Alarm Engine snapshot for {priority_group}'
            ) from error
        if document is None:
            return None
        return GroupRuntimeSnapshot.from_document(document)

    def list_snapshots(self) -> tuple[GroupRuntimeSnapshot, ...]:
        root = self._paths.alarms_root / 'runtime' / 'state' / 'groups'
        if not root.exists():
            return ()
        snapshots: list[GroupRuntimeSnapshot] = []
        for path in sorted(root.glob('*.json')):
            snapshots.append(self._read_snapshot_path(path))
        return tuple(snapshots)

    def read_durable_records(
        self,
        *,
        after: JournalPosition | None = None,
    ) -> tuple[JournalEntry, ...]:
        head = self.read_head()
        if head.durable is None or after == head.durable:
            return ()
        if after is not None and _position_key(after) > _position_key(head.durable):
            raise ValueError('after must not be ahead of durable journal head')
        return tuple(
            entry
            for entry in self._journal.read_entries(after=after, through=head.durable)
            if isinstance(entry.record, EngineCommitRecord)
        )

    def read_durable_adoptions(
        self, *, after: JournalPosition | None = None
    ) -> tuple[JournalEntry, ...]:
        head = self.read_head()
        if head.durable is None or after == head.durable:
            return ()
        if after is not None and _position_key(after) > _position_key(head.durable):
            raise ValueError('after must not be ahead of durable journal head')
        return tuple(
            entry
            for entry in self._journal.read_entries(after=after, through=head.durable)
            if isinstance(entry.record, ConfigurationAdoptionRecord)
        )

    def read_effective_head(self) -> AlarmEffectiveConfigurationHead | None:
        head = self.read_head()
        if not head.aligned:
            raise AlarmRecoveryRequiredError(
                'Alarm Engine journal must be recovered before reading EFFECTIVE'
            )
        entries = self._journal.validate_durable_region(head.durable)
        expected = self._expected_effective_head(entries)
        if expected is None:
            self._assert_effective_absent()
            if self.read_head() != head:
                raise AlarmRecoveryRequiredError('journal changed during EFFECTIVE read')
            return None
        actual = self._read_effective_document()
        if actual != expected:
            raise AlarmRecoveryRequiredError(
                'EFFECTIVE projection requires recovery from the durable WAL'
            )
        self._verify_durable_snapshots(entries)
        if self.read_head() != head:
            raise AlarmRecoveryRequiredError('journal changed during EFFECTIVE read')
        return expected

    def commit_batch(
        self,
        records: Sequence[EngineCommitRecord],
        *,
        assert_authority: AuthorityCheck,
        fenced_mutation: MutationFence,
    ) -> CommitBatchResult:
        authority = _require_authority(assert_authority)
        mutation = _require_mutation_fence(fenced_mutation)
        ordered = _ordered_records(records)
        with self._write_lock:
            return self._commit_records(ordered, authority=authority, mutation=mutation)

    def commit_adoption(
        self,
        record: ConfigurationAdoptionRecord,
        *,
        group_records: Sequence[EngineCommitRecord] = (),
        assert_authority: AuthorityCheck,
        fenced_mutation: MutationFence,
    ) -> CommitBatchResult:
        if not isinstance(record, ConfigurationAdoptionRecord):
            raise TypeError('record must be ConfigurationAdoptionRecord')
        if record.record_hash != build_record_hash(record.unsigned_document()):
            raise AlarmPersistenceValidationError('configuration adoption record hash mismatch')
        if isinstance(group_records, str | bytes) or not isinstance(group_records, Sequence):
            raise TypeError('group_records must be a sequence')
        if isinstance(record, ConfigurationAdoptionRecordV2):
            if not group_records:
                raise AlarmPersistenceValidationError('V2 adoption requires group records')
            ordered_groups = _ordered_records(group_records)
            references = tuple(
                GroupCommitReference(
                    priority_group=item.commit.priority_group,
                    commit_id=item.commit.commit_id,
                    record_hash=item.record_hash,
                )
                for item in ordered_groups
            )
            if references != record.group_commits:
                raise AlarmPersistenceValidationError('V2 adoption group references do not match')
            if any(
                item.commit.alarm_configuration_revision
                != record.target_artifact_ref.alarm_configuration_revision
                or item.commit.tool_registry_revision
                != record.target_artifact_ref.confirmed_tool_catalog_revision
                for item in ordered_groups
            ):
                raise AlarmPersistenceValidationError('V2 group commit revisions must match target')
            if any(
                item.record_hash != build_record_hash(item.unsigned_document())
                for item in ordered_groups
            ):
                raise AlarmPersistenceValidationError('V2 group commit record hash mismatch')
            if segment_id_for_evaluated_at(record.effective_at) != segment_id_for_evaluated_at(
                ordered_groups[0].commit.evaluated_at
            ):
                raise AlarmPersistenceValidationError('V2 adoption must use the same UTC hour')
        else:
            if group_records:
                raise AlarmPersistenceValidationError('V1 adoption cannot include group records')
            ordered_groups = ()
        authority = _require_authority(assert_authority)
        mutation = _require_mutation_fence(fenced_mutation)
        with self._write_lock:
            authority()
            head = self.read_head()
            if not head.aligned:
                raise AlarmRecoveryRequiredError(
                    'Alarm Engine journal must be recovered before committing new work'
                )
            if head.durable is None and self._has_group_snapshots():
                raise AlarmPersistenceCorruptionError(
                    'Alarm Engine snapshots exist without a durable journal head'
                )
            entries = self._journal.validate_durable_region(head.durable)
            adoptions = tuple(
                entry.record
                for entry in entries
                if isinstance(entry.record, ConfigurationAdoptionRecord)
            )
            if not adoptions and entries:
                raise AlarmPersistenceConflictError(
                    'configuration adoption requires explicit legacy state migration'
                )
            previous = None if not adoptions else adoptions[-1].target_artifact_ref
            if record.previous_artifact_ref != previous:
                raise AlarmPersistenceConflictError(
                    'configuration adoption previous artifact does not match durable authority'
                )
            if any(item.adoption_id == record.adoption_id for item in adoptions):
                raise AlarmPersistenceConflictError('configuration adoption_id is already durable')
            return self._commit_records(
                (*ordered_groups, record),
                authority=authority,
                mutation=mutation,
                expected_head=head,
            )

    def _commit_records(
        self,
        records: Sequence[EngineCommitRecord | ConfigurationAdoptionRecord],
        *,
        authority: AuthorityCheck,
        mutation: MutationFence,
        expected_head: JournalHead | None = None,
    ) -> CommitBatchResult:
        authority()
        head = self.read_head()
        if expected_head is not None and head != expected_head:
            raise AlarmPersistenceConflictError(
                'Alarm Engine journal changed during configuration adoption preparation'
            )
        if not head.aligned:
            raise AlarmRecoveryRequiredError(
                'Alarm Engine journal must be recovered before committing new work'
            )
        self.read_effective_head()
        self._validate_previous_state(
            tuple(record for record in records if isinstance(record, EngineCommitRecord))
        )
        first = records[0]
        evaluated_at = (
            first.commit.evaluated_at
            if isinstance(first, EngineCommitRecord)
            else first.effective_at
        )
        segment_id = segment_id_for_evaluated_at(evaluated_at)
        with mutation():
            _require_unchanged_head(self.read_head(), head, stage='WAL append')
            self._journal.discard_unconfirmed_tail(head.durable)
            sealed_count = 0
            if head.durable is not None and segment_id > head.durable.segment_id:
                sealed_count = self._journal.seal_before(segment_id)
            self._journal.verify_append_position(durable=head.durable, segment_id=segment_id)
            entries = self._journal.append_batch(records)
        final_position = entries[-1].end
        durable_head = JournalHead(durable=final_position, materialized=head.materialized)
        with mutation():
            _require_unchanged_head(self.read_head(), head, stage='durable publication')
            self._replace_head(durable_head)
        for entry in entries:
            with mutation():
                _require_durable_head(
                    self.read_head(), durable_head, stage='snapshot materialization'
                )
                self._materialize_entry(entry)
        completed_head = JournalHead(durable=final_position, materialized=final_position)
        with mutation():
            _require_durable_head(self.read_head(), durable_head, stage='materialized publication')
            self._replace_head(completed_head)
        if isinstance(records[-1], ConfigurationAdoptionRecord):
            with mutation():
                _require_unchanged_head(
                    self.read_head(), completed_head, stage='effective publication'
                )
                self._reconcile_effective_head(completed_head)
        return CommitBatchResult(
            record_count=len(entries),
            bytes_appended=sum(entry.end.byte_offset - entry.start_offset for entry in entries),
            durable=final_position,
            materialized=final_position,
            sealed_segment_count=sealed_count,
        )

    def recover(
        self,
        *,
        assert_authority: AuthorityCheck,
        fenced_mutation: MutationFence,
    ) -> RecoveryResult:
        authority = _require_authority(assert_authority)
        mutation = _require_mutation_fence(fenced_mutation)
        with self._write_lock:
            authority()
            head = self.read_head()
            if head.durable is None and self._has_group_snapshots():
                raise AlarmPersistenceCorruptionError(
                    'Alarm Engine snapshots exist without a durable journal head'
                )
            with mutation():
                _require_unchanged_head(self.read_head(), head, stage='recovery tail discard')
                discarded = self._journal.discard_unconfirmed_tail(head.durable)
            authority()
            self._journal.validate_durable_region(head.durable)
            if head.durable is None:
                self._assert_effective_absent()
                return RecoveryResult(
                    durable=None,
                    materialized=None,
                    applied_count=0,
                    skipped_count=0,
                    discarded_tail_bytes=discarded,
                    sealed_segment_count=0,
                )
            if head.materialized == head.durable:
                with mutation():
                    _require_unchanged_head(self.read_head(), head, stage='recovery sealing')
                    sealed_count = self._journal.seal_before(head.durable.segment_id)
                with mutation():
                    _require_unchanged_head(
                        self.read_head(), head, stage='recovery effective publication'
                    )
                    self._reconcile_effective_head(head)
                return RecoveryResult(
                    durable=head.durable,
                    materialized=head.materialized,
                    applied_count=0,
                    skipped_count=0,
                    discarded_tail_bytes=discarded,
                    sealed_segment_count=sealed_count,
                )
            entries = self._journal.read_entries(after=head.materialized, through=head.durable)
            applied = 0
            skipped = 0
            current_materialized = head.materialized
            current_head = head
            batch_end_by_start: dict[int, int] = {}
            for index, entry in enumerate(entries):
                if isinstance(entry.record, ConfigurationAdoptionRecordV2):
                    start = index - len(entry.record.group_commits)
                    if start < 0 or any(
                        isinstance(item.record, ConfigurationAdoptionRecord)
                        for item in entries[start:index]
                    ):
                        raise AlarmPersistenceCorruptionError(
                            'materialized position splits a V2 adoption transaction'
                        )
                    if any(start < other_end for other_end in batch_end_by_start.values()):
                        raise AlarmPersistenceCorruptionError(
                            'V2 adoption transaction boundaries overlap'
                        )
                    batch_end_by_start[start] = index
            index = 0
            while index < len(entries):
                final_index = batch_end_by_start.get(index, index)
                batch = entries[index : final_index + 1]
                for entry in batch:
                    with mutation():
                        _require_unchanged_head(
                            self.read_head(),
                            current_head,
                            stage='recovery snapshot materialization',
                        )
                        was_applied = self._materialize_entry(entry)
                    if was_applied:
                        applied += 1
                    else:
                        skipped += 1
                next_position = batch[-1].end
                next_head = JournalHead(durable=head.durable, materialized=next_position)
                with mutation():
                    _require_unchanged_head(
                        self.read_head(),
                        current_head,
                        stage='recovery materialized publication',
                    )
                    self._replace_head(next_head)
                current_materialized = next_position
                current_head = next_head
                index = final_index + 1
            with mutation():
                _require_unchanged_head(self.read_head(), current_head, stage='recovery sealing')
                sealed_count = self._journal.seal_before(head.durable.segment_id)
            with mutation():
                _require_unchanged_head(
                    self.read_head(), current_head, stage='recovery effective publication'
                )
                self._reconcile_effective_head(current_head)
            return RecoveryResult(
                durable=head.durable,
                materialized=current_materialized,
                applied_count=applied,
                skipped_count=skipped,
                discarded_tail_bytes=discarded,
                sealed_segment_count=sealed_count,
            )

    def _expected_effective_head(
        self, entries: Sequence[JournalEntry]
    ) -> AlarmEffectiveConfigurationHead | None:
        for entry in reversed(entries):
            if isinstance(entry.record, ConfigurationAdoptionRecord):
                return AlarmEffectiveConfigurationHead.from_adoption_entry(entry)
        return None

    def _read_effective_document(self) -> AlarmEffectiveConfigurationHead | None:
        try:
            document = self._state.read(self._paths.effective_head_relative)
        except StateError as error:
            raise AlarmPersistenceCorruptionError(
                'could not read Alarm Engine effective head'
            ) from error
        if document is None:
            return None
        return AlarmEffectiveConfigurationHead.from_document(document)

    def _assert_effective_absent(self) -> None:
        if self._read_effective_document() is not None:
            raise AlarmPersistenceCorruptionError(
                'EFFECTIVE projection exists without a durable adoption'
            )

    def _verify_durable_snapshots(self, entries: Sequence[JournalEntry]) -> None:
        latest = {
            entry.record.commit.priority_group: entry.record.snapshot_after
            for entry in entries
            if isinstance(entry.record, EngineCommitRecord)
        }
        snapshots = self.list_snapshots()
        actual = {snapshot.priority_group: snapshot for snapshot in snapshots}
        if (
            len(actual) != len(snapshots)
            or set(actual) != set(latest)
            or any(actual[group] != expected for group, expected in latest.items())
        ):
            raise AlarmPersistenceCorruptionError(
                'group snapshots do not match the durable journal before EFFECTIVE publication'
            )

    def _write_effective_head(self, head: AlarmEffectiveConfigurationHead) -> None:
        try:
            self._state.replace(self._paths.effective_head_relative, head.as_document())
        except StateError as error:
            raise AlarmPersistenceWriteError('could not publish Alarm Engine EFFECTIVE') from error

    def _reconcile_effective_head(self, expected_journal_head: JournalHead) -> None:
        if not expected_journal_head.aligned or self.read_head() != expected_journal_head:
            raise AlarmRecoveryRequiredError(
                'journal must be aligned and unchanged before EFFECTIVE publication'
            )
        entries = self._journal.validate_durable_region(expected_journal_head.durable)
        expected = self._expected_effective_head(entries)
        if expected is None:
            self._assert_effective_absent()
            return
        self._verify_durable_snapshots(entries)
        try:
            actual = self._read_effective_document()
        except AlarmPersistenceCorruptionError:
            actual = None
        if actual != expected:
            self._write_effective_head(expected)

    def _validate_previous_state(self, records: Sequence[EngineCommitRecord]) -> None:
        for record in records:
            current = self.read_snapshot(record.commit.priority_group)
            if current is None:
                if record.commit.previous_commit_id is not None:
                    raise AlarmPersistenceConflictError(
                        'engine commit previous_commit_id does not match current group head'
                    )
                continue
            if current.last_commit_id == record.commit.commit_id:
                raise AlarmPersistenceConflictError('engine commit is already materialized')
            if current.last_commit_id != record.commit.previous_commit_id:
                raise AlarmPersistenceConflictError(
                    'engine commit previous_commit_id does not match current group head'
                )

    def _materialize_entry(self, entry: JournalEntry) -> bool:
        record = entry.record
        if isinstance(record, ConfigurationAdoptionRecord):
            return True
        current = self.read_snapshot(record.commit.priority_group)
        if current is not None and current.last_commit_id == record.commit.commit_id:
            return False
        expected = record.commit.previous_commit_id
        if current is None:
            if expected is not None:
                raise AlarmPersistenceCorruptionError(
                    'group snapshot is missing before a non-initial durable commit'
                )
        elif current.last_commit_id != expected:
            raise AlarmPersistenceCorruptionError(
                'group snapshot head does not match durable commit chain'
            )
        try:
            self._state.replace(
                self._paths.group_snapshot_relative(record.commit.priority_group),
                record.snapshot_after.as_document(),
            )
        except StateError as error:
            raise AlarmPersistenceWriteError(
                'could not materialize Alarm Engine snapshot'
            ) from error
        return True

    def _replace_head(self, head: JournalHead) -> None:
        try:
            self._state.replace(self._paths.journal_head_relative, head.as_document())
        except StateError as error:
            raise AlarmPersistenceWriteError(
                'could not publish Alarm Engine journal head'
            ) from error

    def _read_snapshot_path(self, path: Path) -> GroupRuntimeSnapshot:
        try:
            relative = path.relative_to(self._paths.alarms_root)
            document = self._state.read(relative)
        except (StateError, ValueError) as error:
            raise AlarmPersistenceCorruptionError('could not read Alarm Engine snapshot') from error
        if document is None:
            raise AlarmPersistenceCorruptionError('Alarm Engine snapshot disappeared during read')
        return GroupRuntimeSnapshot.from_document(document)

    def _has_group_snapshots(self) -> bool:
        root = self._paths.alarms_root / 'runtime' / 'state' / 'groups'
        return root.exists() and any(root.glob('*.json'))


# Aplica las validaciones necesarias para preservar los invariantes durables.
def _require_authority(value: AuthorityCheck) -> AuthorityCheck:
    if not callable(value):
        raise TypeError('assert_authority must be callable')
    return value


# Aplica las validaciones necesarias para preservar los invariantes durables.
def _require_mutation_fence(value: MutationFence) -> MutationFence:
    if not callable(value):
        raise TypeError('fenced_mutation must be callable')
    return value


# Aplica las validaciones necesarias para preservar los invariantes durables.
def _require_unchanged_head(current: JournalHead, expected: JournalHead, *, stage: str) -> None:
    if current != expected:
        raise AlarmPersistenceConflictError(f'Alarm Engine journal head changed before {stage}')


# Aplica las validaciones necesarias para preservar los invariantes durables.
def _require_durable_head(current: JournalHead, expected: JournalHead, *, stage: str) -> None:
    if current.durable != expected.durable or current.materialized != expected.materialized:
        raise AlarmPersistenceConflictError(f'Alarm Engine journal head changed before {stage}')


# Aplica las validaciones necesarias para preservar los invariantes durables.
def _ordered_records(records: Sequence[EngineCommitRecord]) -> tuple[EngineCommitRecord, ...]:
    if isinstance(records, str | bytes) or not isinstance(records, Sequence):
        raise TypeError('records must be a sequence')
    if not records:
        raise ValueError('records must not be empty')
    normalized: list[EngineCommitRecord] = []
    cycle_id: str | None = None
    groups: set[str] = set()
    segment_id: str | None = None
    for record in records:
        if not isinstance(record, EngineCommitRecord):
            raise TypeError('records must contain only EngineCommitRecord values')
        if cycle_id is None:
            cycle_id = record.commit.cycle_id
        elif record.commit.cycle_id != cycle_id:
            raise ValueError('all records in a batch must share cycle_id')
        if record.commit.priority_group in groups:
            raise ValueError('a batch must contain at most one commit per priority_group')
        groups.add(record.commit.priority_group)
        current_segment = segment_id_for_evaluated_at(record.commit.evaluated_at)
        if segment_id is None:
            segment_id = current_segment
        elif current_segment != segment_id:
            raise ValueError('all records in a batch must belong to the same UTC hour')
        normalized.append(record)
    return tuple(
        sorted(normalized, key=lambda item: (item.commit.priority_group, item.commit.commit_id))
    )


# Aplica las validaciones necesarias para preservar los invariantes durables.
def _position_key(value: JournalPosition) -> tuple[str, int]:
    return value.segment_id, value.byte_offset
