from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ada.alarms.persistence.operational.configuration_adoption import (
    AlarmArtifactRefSnapshot,
    ConfigurationAdoptionRecord,
)
from ada.alarms.persistence.operational.durable_provenance import AttributedDurableEntry
from ada.alarms.persistence.operational.effective_head import AlarmEffectiveConfigurationHead
from ada.alarms.persistence.operational.errors import AlarmRecoveryRequiredError
from ada.alarms.persistence.operational.models import (
    CommitBatchResult,
    EngineCommitRecord,
    JournalEntry,
    JournalHead,
    JournalPosition,
    RecoveryResult,
)
from ada.alarms.persistence.operational.store import (
    AlarmPersistence,
    AuthorityCheck,
    MutationFence,
)


@dataclass(frozen=True, slots=True)
class _RecentCommittedBatch:
    prior_position: JournalPosition | None
    final_head: JournalHead
    entries: tuple[JournalEntry, ...]
    artifact_ref: AlarmArtifactRefSnapshot


class IncrementalAlarmPersistence(AlarmPersistence):
    def __init__(
        self, *, application_root: str | Path, max_state_document_bytes: int | None = None
    ) -> None:
        super().__init__(
            application_root=application_root,
            max_state_document_bytes=max_state_document_bytes,
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
            effective = super().read_effective_head()
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
            return super().read_durable_provenance(after=after)

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
                entry.record != record
                for entry, record in zip(entries, records, strict=True)
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

    def recover(
        self,
        *,
        assert_authority: AuthorityCheck,
        fenced_mutation: MutationFence,
    ) -> RecoveryResult:
        with self._write_lock:
            self._invalidate_verified_state()
            try:
                result = super().recover(
                    assert_authority=assert_authority,
                    fenced_mutation=fenced_mutation,
                )
                self.read_effective_head()
                return result
            except BaseException:
                self._invalidate_verified_state()
                raise
