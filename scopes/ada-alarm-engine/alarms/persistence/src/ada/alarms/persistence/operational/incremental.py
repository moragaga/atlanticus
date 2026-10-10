from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ada.alarms.persistence.operational.configuration_adoption import (
    AlarmArtifactRefSnapshot,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    GroupCommitReference,
)
from ada.alarms.persistence.operational.durable_provenance import AttributedDurableEntry
from ada.alarms.persistence.operational.effective_head import AlarmEffectiveConfigurationHead
from ada.alarms.persistence.operational.errors import (
    AlarmPersistenceConflictError,
    AlarmPersistenceCorruptionError,
    AlarmPersistenceWriteError,
    AlarmRecoveryRequiredError,
)
from ada.alarms.persistence.operational.models import (
    CommitBatchResult,
    EngineCommitRecord,
    JournalEntry,
    JournalHead,
    JournalPosition,
    RecoveryResult,
)
from ada.alarms.persistence.operational.recovery_checkpoint import (
    RecoveryCheckpoint,
    latest_checkpoint,
)
from ada.alarms.persistence.operational.store import (
    AlarmPersistence,
    AuthorityCheck,
    MutationFence,
)
from atlanticus.state import StateError


@dataclass(frozen=True, slots=True)
class _RecentCommittedBatch:
    prior_position: JournalPosition | None
    final_head: JournalHead
    entries: tuple[JournalEntry, ...]
    artifact_ref: AlarmArtifactRefSnapshot


class IncrementalAlarmPersistence(AlarmPersistence):
    def __init__(
        self,
        *,
        application_root: str | Path,
        max_state_document_bytes: int | None = None,
        max_journal_segment_bytes: int = 262144,
    ) -> None:
        super().__init__(
            application_root=application_root,
            max_state_document_bytes=max_state_document_bytes,
            max_journal_segment_bytes=max_journal_segment_bytes,
        )
        self._verified_head: JournalHead | None = None
        self._verified_effective: AlarmEffectiveConfigurationHead | None = None
        self._recent_batch: _RecentCommittedBatch | None = None

    def _invalidate_verified_state(self) -> None:
        self._verified_head = None
        self._verified_effective = None
        self._recent_batch = None

    def read_effective_head(self) -> AlarmEffectiveConfigurationHead | None:
        with self._write_lock:
            head = self.read_head()
            if self._verified_head is not None and self._verified_head == head and head.aligned:
                try:
                    current = self._read_effective_document()
                except BaseException:
                    self._invalidate_verified_state()
                    raise
                if current != self._verified_effective:
                    self._invalidate_verified_state()
                    raise AlarmRecoveryRequiredError(
                        'EFFECTIVE changed after validated incremental authority'
                    )
                if self.read_head() != head:
                    self._invalidate_verified_state()
                    raise AlarmRecoveryRequiredError(
                        'journal changed during incremental EFFECTIVE read'
                    )
                return current
            self._invalidate_verified_state()
            tail = self._checkpoint_tail(head) if head.aligned else None
            if tail is None:
                effective = super().read_effective_head()
            else:
                _, _, effective, snapshots = tail
                self._verify_checkpoint_snapshots(snapshots)
                if self._read_effective_document() != effective:
                    raise AlarmRecoveryRequiredError('EFFECTIVE differs from checkpoint suffix')
            self._verified_head = head
            self._verified_effective = effective
            return effective

    def read_durable_provenance(
        self, *, after: JournalPosition | None = None
    ) -> tuple[AttributedDurableEntry, ...]:
        with self._write_lock:
            head = self.read_head()
            batch = self._recent_batch
            if (
                batch is not None
                and head.aligned
                and self._verified_head == head
                and batch.final_head == head
                and batch.prior_position == after
            ):
                self.read_effective_head()
                entries = self._journal.read_entries(after=after, through=head.durable)
                if entries != batch.entries:
                    self._invalidate_verified_state()
                    raise AlarmRecoveryRequiredError(
                        'newly committed journal records differ from validated batch'
                    )
                if self.read_head() != head:
                    self._invalidate_verified_state()
                    raise AlarmRecoveryRequiredError(
                        'journal changed during incremental provenance read'
                    )
                return tuple(
                    AttributedDurableEntry(entry=entry, artifact_ref=batch.artifact_ref)
                    for entry in entries
                )
            if (
                after is not None
                and after == head.durable
                and head.aligned
                and self._verified_head == head
            ):
                self.read_effective_head()
                return ()
            tail = self._checkpoint_tail(head) if head.aligned else None
            if tail is None:
                return super().read_durable_provenance(after=after)
            checkpoint, entries, _, _ = tail
            anchor = JournalPosition.from_document(checkpoint.journal_head['durable'])
            if after is None or (after.segment_id, after.byte_offset) < (
                anchor.segment_id,
                anchor.byte_offset,
            ):
                return super().read_durable_provenance(after=after)
            if after == anchor:
                selected = entries
            else:
                selected = None
                for index, entry in enumerate(entries):
                    if entry.end == after:
                        selected = entries[index + 1 :]
                        break
                if selected is None:
                    raise ValueError('after must identify an exact durable journal entry boundary')
            targets: dict[int, AlarmArtifactRefSnapshot] = {}
            for index, entry in enumerate(entries):
                adoption = entry.record
                if isinstance(adoption, ConfigurationAdoptionRecordV2):
                    for offset in range(len(adoption.group_commits)):
                        targets[index - len(adoption.group_commits) + offset] = (
                            adoption.target_artifact_ref
                        )
            artifact = AlarmEffectiveConfigurationHead.from_document(
                checkpoint.effective_head
            ).target_artifact_ref
            attributed = []
            for index, entry in enumerate(entries):
                if isinstance(entry.record, ConfigurationAdoptionRecord):
                    artifact = entry.record.target_artifact_ref
                    ref = artifact
                else:
                    ref = targets.get(index, artifact)
                    if (
                        entry.record.commit.alarm_configuration_revision
                        != ref.alarm_configuration_revision
                        or entry.record.commit.tool_registry_revision
                        != ref.confirmed_tool_catalog_revision
                    ):
                        raise AlarmPersistenceCorruptionError(
                            'checkpoint provenance revisions differ'
                        )
                if entry in selected:
                    attributed.append(AttributedDurableEntry(entry=entry, artifact_ref=ref))
            return tuple(attributed)

    def _commit_records(
        self,
        records: Sequence[EngineCommitRecord | ConfigurationAdoptionRecord],
        *,
        authority: AuthorityCheck,
        mutation: MutationFence,
        expected_head: JournalHead | None = None,
    ) -> CommitBatchResult:
        prior = self.read_head()
        try:
            result = super()._commit_records(
                records,
                authority=authority,
                mutation=mutation,
                expected_head=expected_head,
            )
            head = self.read_head()
            if not head.aligned or head.durable != result.durable:
                raise AlarmRecoveryRequiredError(
                    'newly committed journal did not reach an aligned durable head'
                )
            effective = self._read_effective_document()
            last_record = records[-1]
            if isinstance(last_record, ConfigurationAdoptionRecord):
                artifact_ref = last_record.target_artifact_ref
                if effective is None or effective.target_artifact_ref != artifact_ref:
                    raise AlarmRecoveryRequiredError(
                        'newly committed adoption differs from EFFECTIVE'
                    )
            else:
                if effective is None or effective != self._verified_effective:
                    raise AlarmRecoveryRequiredError(
                        'EFFECTIVE changed during ordinary group commit'
                    )
                artifact_ref = effective.target_artifact_ref
            entries = self._journal.read_entries(after=prior.durable, through=head.durable)
            if len(entries) != len(records) or any(
                entry.record != record for entry, record in zip(entries, records, strict=True)
            ):
                raise AlarmRecoveryRequiredError(
                    'newly committed journal entries differ from accepted records'
                )
            self._verified_head = head
            self._verified_effective = effective
            self._recent_batch = _RecentCommittedBatch(
                prior_position=prior.durable,
                final_head=head,
                entries=entries,
                artifact_ref=artifact_ref,
            )
            return result
        except BaseException:
            self._invalidate_verified_state()
            raise

    def _checkpoint_tail(
        self, head: JournalHead
    ) -> (
        tuple[
            RecoveryCheckpoint,
            tuple[JournalEntry, ...],
            AlarmEffectiveConfigurationHead,
            dict[str, dict[str, object]],
        ]
        | None
    ):
        checkpoint = latest_checkpoint(self._checkpoint_slots())
        if checkpoint is None or head.durable is None:
            return None
        anchor = JournalPosition.from_document(checkpoint.journal_head['durable'])
        if (head.durable.segment_id, head.durable.byte_offset) < (
            anchor.segment_id,
            anchor.byte_offset,
        ):
            raise AlarmPersistenceCorruptionError('durable WAL is behind recovery checkpoint')
        if self._wal_anchor_sha256(anchor) != checkpoint.wal_anchor_sha256:
            raise AlarmPersistenceCorruptionError('checkpoint WAL anchor changed')
        effective = AlarmEffectiveConfigurationHead.from_document(checkpoint.effective_head)
        group_states = {group['priority_group']: group for group in checkpoint.groups}
        group_commits = {name: group['last_commit_id'] for name, group in group_states.items()}
        entries = (
            ()
            if anchor == head.durable
            else self._journal.read_entries(after=anchor, through=head.durable)
        )
        artifact = effective.target_artifact_ref
        pending_adoption_targets: dict[int, AlarmArtifactRefSnapshot] = {}
        for index, entry in enumerate(entries):
            adoption = entry.record
            if isinstance(adoption, ConfigurationAdoptionRecordV2):
                count = len(adoption.group_commits)
                for offset in range(count):
                    pending_adoption_targets[index - count + offset] = adoption.target_artifact_ref
        for index, entry in enumerate(entries):
            record = entry.record
            if isinstance(record, ConfigurationAdoptionRecord):
                if record.previous_artifact_ref != artifact:
                    raise AlarmPersistenceCorruptionError(
                        'checkpoint adoption chain is discontinuous'
                    )
                if isinstance(record, ConfigurationAdoptionRecordV2):
                    count = len(record.group_commits)
                    preceding = entries[index - count : index] if index >= count else ()
                    references = tuple(
                        GroupCommitReference(
                            priority_group=item.record.commit.priority_group,
                            commit_id=item.record.commit.commit_id,
                            record_hash=item.record.record_hash,
                        )
                        for item in preceding
                        if isinstance(item.record, EngineCommitRecord)
                    )
                    if (
                        len(preceding) != count
                        or references != record.group_commits
                        or any(item.end.segment_id != entry.end.segment_id for item in preceding)
                    ):
                        raise AlarmPersistenceCorruptionError(
                            'checkpoint V2 adoption references are invalid'
                        )
                artifact = record.target_artifact_ref
                effective = AlarmEffectiveConfigurationHead.from_adoption_entry(entry)
                continue
            commit = record.commit
            origin = pending_adoption_targets.get(index, artifact)
            if (
                commit.alarm_configuration_revision != origin.alarm_configuration_revision
                or commit.tool_registry_revision != origin.confirmed_tool_catalog_revision
            ):
                raise AlarmPersistenceCorruptionError('checkpoint commit artifact differs')
            if commit.previous_commit_id != group_commits.get(commit.priority_group):
                raise AlarmPersistenceCorruptionError(
                    'checkpoint group commit chain is discontinuous'
                )
            group_commits[commit.priority_group] = commit.commit_id
            group_states[commit.priority_group] = record.snapshot_after.as_document()
        return checkpoint, tuple(entries), effective, group_states

    def _verify_checkpoint_snapshots(self, expected: dict[str, dict[str, object]]) -> None:
        snapshots = self.list_snapshots()
        actual = {item.priority_group: item.as_document() for item in snapshots}
        if len(actual) != len(snapshots) or actual != expected:
            raise AlarmPersistenceCorruptionError(
                'group snapshots differ from checkpoint WAL suffix'
            )

    def _reconcile_effective_head(self, expected_journal_head: JournalHead) -> None:
        tail = self._checkpoint_tail(expected_journal_head)
        if tail is None:
            return super()._reconcile_effective_head(expected_journal_head)
        if not expected_journal_head.aligned or self.read_head() != expected_journal_head:
            raise AlarmRecoveryRequiredError('journal must be aligned for EFFECTIVE publication')
        _, _, effective, snapshots = tail
        self._verify_checkpoint_snapshots(snapshots)
        try:
            current = self._read_effective_document()
        except AlarmPersistenceCorruptionError:
            current = None
        if current != effective:
            self._write_effective_head(effective)

    def _recover_checkpoint_suffix(
        self, *, assert_authority: AuthorityCheck, fenced_mutation: MutationFence
    ) -> RecoveryResult | None:
        assert_authority()
        head = self.read_head()
        tail = self._checkpoint_tail(head)
        if tail is None:
            return None
        checkpoint, entries, effective, expected_snapshots = tail
        with fenced_mutation():
            if self.read_head() != head:
                raise AlarmPersistenceConflictError('WAL changed during suffix recovery')
            discarded = self._journal.discard_unconfirmed_tail(head.durable)
        if head.aligned:
            self._verify_checkpoint_snapshots(expected_snapshots)
            if self._read_effective_document() != effective:
                with fenced_mutation():
                    if self.read_head() != head:
                        raise AlarmPersistenceConflictError(
                            'WAL advanced before EFFECTIVE recovery'
                        )
                    self._reconcile_effective_head(head)
            aligned = head
            applied = skipped = 0
        else:
            position = JournalPosition.from_document(checkpoint.journal_head['durable'])
            if head.materialized is None or (
                head.materialized.segment_id,
                head.materialized.byte_offset,
            ) < (position.segment_id, position.byte_offset):
                raise AlarmPersistenceCorruptionError('WAL materialization is behind checkpoint')
            pending = [
                entry
                for entry in entries
                if (entry.end.segment_id, entry.end.byte_offset)
                > (head.materialized.segment_id, head.materialized.byte_offset)
            ]
            if pending and pending[-1].end != head.durable:
                raise AlarmPersistenceCorruptionError('WAL suffix does not reach durable position')
            grouped: dict[int, int] = {}
            for index, entry in enumerate(pending):
                if isinstance(entry.record, ConfigurationAdoptionRecordV2):
                    start = index - len(entry.record.group_commits)
                    if start < 0:
                        raise AlarmPersistenceCorruptionError(
                            'materialized position splits V2 adoption'
                        )
                    grouped[start] = index
            current_head = head
            applied = skipped = 0
            index = 0
            while index < len(pending):
                end_index = grouped.get(index, index)
                batch = pending[index : end_index + 1]
                for item in batch:
                    with fenced_mutation():
                        if self.read_head() != current_head:
                            raise AlarmPersistenceConflictError(
                                'WAL advanced during suffix materialization'
                            )
                        result = self._materialize_entry(item)
                    applied += int(result)
                    skipped += int(not result)
                next_head = JournalHead(durable=head.durable, materialized=batch[-1].end)
                with fenced_mutation():
                    if self.read_head() != current_head:
                        raise AlarmPersistenceConflictError('WAL advanced during suffix recovery')
                    self._replace_head(next_head)
                current_head = next_head
                index = end_index + 1
            aligned = self.read_head()
            if not aligned.aligned:
                raise AlarmRecoveryRequiredError('checkpoint suffix recovery is not aligned')
            self._verify_checkpoint_snapshots(expected_snapshots)
            with fenced_mutation():
                self._reconcile_effective_head(aligned)
        with fenced_mutation():
            if self.read_head() != aligned:
                raise AlarmPersistenceConflictError('WAL advanced during suffix sealing')
            sealed = self._journal.seal_before(aligned.durable.segment_id)
        self._verified_head = aligned
        self._verified_effective = effective
        self._recent_batch = None
        return RecoveryResult(
            durable=aligned.durable,
            materialized=aligned.materialized,
            applied_count=applied,
            skipped_count=skipped,
            discarded_tail_bytes=discarded,
            sealed_segment_count=sealed,
        )

    def compact_recovered_wal(
        self,
        *,
        exported_through: JournalPosition | None,
        assert_authority: AuthorityCheck,
        fenced_mutation: MutationFence,
    ) -> int:
        with self._write_lock:
            assert_authority()
            head = self.read_head()
            if not head.aligned or head.durable is None or exported_through != head.durable:
                return 0
            slots = self._checkpoint_slots()
            if any(item is None for item in slots):
                return 0
            ordered = sorted(slots, key=lambda item: item.sequence)
            newest = ordered[-1]
            if newest.journal_head != head.as_document():
                return 0
            self._checkpoint_tail(head)
            self._verify_checkpoint_snapshots(
                {group['priority_group']: group for group in newest.groups}
            )
            older_position = JournalPosition.from_document(ordered[0].journal_head['durable'])
            if (older_position.segment_id, older_position.byte_offset) >= (
                head.durable.segment_id,
                head.durable.byte_offset,
            ):
                return 0
            cutoff = older_position.segment_id
            for checkpoint in ordered:
                position = JournalPosition.from_document(checkpoint.journal_head['durable'])
                if self._wal_anchor_sha256(position) != checkpoint.wal_anchor_sha256:
                    raise AlarmPersistenceCorruptionError('checkpoint backup WAL anchor differs')
            candidates = sorted(
                (segment_id, path)
                for segment_id, path in self._journal._discover_sealed_segments().items()
                if segment_id < cutoff
            )
            removed = 0
            for _, path in candidates:
                with fenced_mutation():
                    if self.read_head() != head or self._checkpoint_slots() != slots:
                        raise AlarmPersistenceConflictError('WAL advanced during compaction')
                    if self._wal_anchor_sha256(head.durable) != newest.wal_anchor_sha256:
                        raise AlarmPersistenceCorruptionError('checkpoint WAL anchor changed')
                    try:
                        size = path.stat().st_size
                        path.unlink()
                        fd = os.open(path.parent, os.O_RDONLY)
                        try:
                            os.fsync(fd)
                        finally:
                            os.close(fd)
                    except OSError as error:
                        raise AlarmPersistenceWriteError(
                            'could not remove compacted WAL segment'
                        ) from error
                removed += size
            return removed

    def recover(
        self,
        *,
        assert_authority: AuthorityCheck,
        fenced_mutation: MutationFence,
    ) -> RecoveryResult:
        with self._write_lock:
            self._invalidate_verified_state()
            try:
                recovered = self._recover_exact_checkpoint(
                    assert_authority=assert_authority,
                    fenced_mutation=fenced_mutation,
                )
                if recovered is not None:
                    return recovered
                result = self._recover_checkpoint_suffix(
                    assert_authority=assert_authority,
                    fenced_mutation=fenced_mutation,
                )
                if result is None:
                    result = super().recover(
                        assert_authority=assert_authority,
                        fenced_mutation=fenced_mutation,
                    )
                self.read_effective_head()
                return result
            except BaseException:
                self._invalidate_verified_state()
                raise

    def _checkpoint_slots(self) -> tuple[RecoveryCheckpoint | None, RecoveryCheckpoint | None]:
        try:
            first = self._state.read('runtime/state/recovery-checkpoint-0.json')
            second = self._state.read('runtime/state/recovery-checkpoint-1.json')
            values = (
                None if first is None else RecoveryCheckpoint.from_document(first),
                None if second is None else RecoveryCheckpoint.from_document(second),
            )
            latest_checkpoint(values)
            return values
        except (StateError, ValueError, TypeError) as error:
            raise AlarmPersistenceCorruptionError('recovery checkpoint is invalid') from error

    def _wal_anchor_sha256(self, position: JournalPosition) -> str:
        path = self._journal._resolve_segment_path(position.segment_id)
        if path is None:
            raise AlarmPersistenceCorruptionError('checkpoint WAL anchor is missing')
        import hashlib

        digest = hashlib.sha256()
        remaining = position.byte_offset
        try:
            with path.open('rb') as handle:
                while remaining:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        raise AlarmPersistenceCorruptionError('checkpoint WAL anchor is truncated')
                    digest.update(chunk)
                    remaining -= len(chunk)
        except OSError as error:
            raise AlarmPersistenceCorruptionError('checkpoint WAL anchor cannot be read') from error
        return digest.hexdigest()

    def publish_recovery_checkpoint(
        self, *, assert_authority: AuthorityCheck, fenced_mutation: MutationFence
    ) -> bool:
        with self._write_lock:
            assert_authority()
            head = self.read_head()
            if not head.aligned or head.durable is None:
                return False
            effective = self.read_effective_head()
            if effective is None:
                raise AlarmRecoveryRequiredError('recovery checkpoint requires EFFECTIVE')
            groups = tuple(snapshot.as_document() for snapshot in self.list_snapshots())
            existing = self._checkpoint_slots()
            current = latest_checkpoint(existing)
            base = RecoveryCheckpoint.create(
                sequence=1 if current is None else current.sequence + 1,
                journal_head=head.as_document(),
                effective_head=effective.as_document(),
                groups=groups,
                wal_anchor_sha256=self._wal_anchor_sha256(head.durable),
            )
            if current is not None and (
                current.journal_head == base.journal_head
                and current.effective_head == base.effective_head
                and current.groups == base.groups
                and current.wal_anchor_sha256 == base.wal_anchor_sha256
            ):
                return False
            slot = base.sequence % 2
            with fenced_mutation():
                if self.read_head() != head:
                    raise AlarmPersistenceConflictError(
                        'WAL advanced during checkpoint publication'
                    )
                if self._read_effective_document() != effective:
                    raise AlarmPersistenceConflictError('EFFECTIVE changed during checkpoint')
                if tuple(item.as_document() for item in self.list_snapshots()) != groups:
                    raise AlarmPersistenceConflictError('snapshots changed during checkpoint')
                if self._wal_anchor_sha256(head.durable) != base.wal_anchor_sha256:
                    raise AlarmPersistenceCorruptionError('WAL anchor changed during checkpoint')
                if self._checkpoint_slots() != existing:
                    raise AlarmPersistenceConflictError('checkpoint generation changed')
                try:
                    self._state.replace(
                        f'runtime/state/recovery-checkpoint-{slot}.json',
                        base.as_document(),
                    )
                except StateError as error:
                    raise AlarmPersistenceWriteError(
                        'could not publish recovery checkpoint'
                    ) from error
            return True

    def _recover_exact_checkpoint(
        self, *, assert_authority: AuthorityCheck, fenced_mutation: MutationFence
    ) -> RecoveryResult | None:
        head = self.read_head()
        if not head.aligned or head.durable is None:
            return None
        checkpoint = latest_checkpoint(self._checkpoint_slots())
        if checkpoint is None or checkpoint.journal_head != head.as_document():
            return None
        assert_authority()
        effective = self._read_effective_document()
        if effective is None or effective.as_document() != checkpoint.effective_head:
            raise AlarmPersistenceCorruptionError('EFFECTIVE differs from recovery checkpoint')
        groups = tuple(snapshot.as_document() for snapshot in self.list_snapshots())
        if groups != checkpoint.groups:
            raise AlarmPersistenceCorruptionError('snapshots differ from recovery checkpoint')
        if self._wal_anchor_sha256(head.durable) != checkpoint.wal_anchor_sha256:
            raise AlarmPersistenceCorruptionError('WAL anchor differs from recovery checkpoint')
        with fenced_mutation():
            if self.read_head() != head:
                raise AlarmPersistenceConflictError('WAL advanced during checkpoint recovery')
            discarded = self._journal.discard_unconfirmed_tail(head.durable)
        if self._wal_anchor_sha256(head.durable) != checkpoint.wal_anchor_sha256:
            raise AlarmPersistenceCorruptionError('checkpoint WAL changed during recovery')
        with fenced_mutation():
            if self.read_head() != head:
                raise AlarmPersistenceConflictError('WAL advanced during checkpoint sealing')
            sealed = self._journal.seal_before(head.durable.segment_id)
        if self.read_head() != head:
            raise AlarmPersistenceConflictError('WAL advanced during checkpoint recovery')
        self._verified_head = head
        self._verified_effective = effective
        self._recent_batch = None
        return RecoveryResult(
            durable=head.durable,
            materialized=head.materialized,
            applied_count=0,
            skipped_count=0,
            discarded_tail_bytes=discarded,
            sealed_segment_count=sealed,
        )
