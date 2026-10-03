from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from atlanticus.web.users.recovery import (
    ToolUsersRecoveryService,
    ToolUsersRecoverySnapshot,
    UsersRecoveryConflictError,
    UsersReplaceValidation,
)


@dataclass(frozen=True, slots=True)
class UsersProjectionWorkflow:
    recovery: ToolUsersRecoveryService | Callable[[], ToolUsersRecoveryService]
    snapshot_ids: Callable[[], tuple[str, ...]]
    operator_id: Callable[[], str]
    snapshot_summaries: Callable[[], tuple[tuple[str, str | None], ...]] | None = None
    read_snapshot: Callable[[str], ToolUsersRecoverySnapshot] | None = None

    def _service(self) -> ToolUsersRecoveryService:
        return self.recovery() if callable(self.recovery) else self.recovery

    def history(self) -> tuple[str, ...]:
        return self.snapshot_ids()

    def history_details(self) -> tuple[dict[str, str | None], ...]:
        summaries = (
            self.snapshot_summaries()
            if self.snapshot_summaries is not None
            else tuple((snapshot_id, None) for snapshot_id in self.history())
        )
        return tuple(
            {'snapshot_id': snapshot_id, 'saved_at_utc': saved_at_utc}
            for snapshot_id, saved_at_utc in summaries
        )

    def describe_snapshot(self, snapshot_id: str) -> dict[str, object]:
        if self.read_snapshot is None:
            raise UsersRecoveryConflictError('Snapshot details provider is required')
        requested_id = _required(snapshot_id, 'Snapshot id')
        snapshot = self.read_snapshot(requested_id)
        if snapshot.snapshot_id != requested_id:
            raise UsersRecoveryConflictError('Snapshot details do not match the selected id')
        return {
            'snapshot_id': snapshot.snapshot_id,
            'captured_at_utc': snapshot.captured_at_utc,
            'origin_environment': snapshot.origin_environment,
            'approved_count': len(snapshot.users),
            'approval_reference': snapshot.approval_reference,
            'operator_id': snapshot.operator_id,
            'tool_key': snapshot.tool_key,
        }

    def preview_capture(self) -> dict[str, object]:
        preview = self._service().preview_capture()
        return {
            'digest': preview.content_digest,
            'approved_ids': [user.user_id for user in preview.users],
            'candidate_ids': [],
        }

    def capture(self, preview: dict[str, object], approval_reference: str) -> dict[str, object]:
        reference = _approval_reference(approval_reference)
        service = self._service()
        fresh = service.preview_capture()
        current = {
            'digest': fresh.content_digest,
            'approved_ids': [user.user_id for user in fresh.users],
            'candidate_ids': [],
        }
        if preview != current:
            raise UsersRecoveryConflictError('Capture preview changed; review the current state')
        result = service.capture(
            preview=fresh,
            approved_user_ids=tuple(current['approved_ids']),
            operator_id=_required(self.operator_id(), 'Operator id'),
            approval_reference=reference,
            confirmed=True,
        )
        return {
            'snapshot_id': result.snapshot_id,
            'digest': result.content_digest,
            'approved_count': len(result.users),
            'origin_environment': result.origin_environment,
        }

    def inspect(self, snapshot_id: str) -> dict[str, object]:
        return _inspection(self._service().validate_replace(_required(snapshot_id, 'Snapshot id')))

    def apply(
        self,
        *,
        inspection: dict[str, object],
        approval_reference: str,
        maintenance_confirmed: bool,
        revocations_reviewed: bool,
        confirmed: bool,
    ) -> dict[str, object]:
        if not isinstance(inspection, dict) or confirmed is not True:
            raise UsersRecoveryConflictError('Inspect a snapshot before applying changes')
        if maintenance_confirmed is not True or revocations_reviewed is not True:
            raise UsersRecoveryConflictError('Maintenance and revocation review are required')
        reference = _approval_reference(approval_reference)
        snapshot_id = _required(inspection.get('snapshot_id'), 'Snapshot id')
        service = self._service()
        fresh = service.validate_replace(snapshot_id)
        if inspection != _inspection(fresh):
            raise UsersRecoveryConflictError('Users runtime changed; inspect the snapshot again')
        if not fresh.differences:
            raise UsersRecoveryConflictError('Users runtime is already aligned with the snapshot')
        operation_id = uuid4().hex
        after = service.replace_snapshot(
            snapshot_id=snapshot_id,
            operator_id=_required(self.operator_id(), 'Operator id'),
            approval_reference=reference,
            operation_id=operation_id,
            confirmed=True,
            maintenance_confirmed=True,
            revocations_reviewed=True,
        )
        if after.differences:
            raise UsersRecoveryConflictError('Users runtime replacement did not align the target')
        return {
            'operation_id': operation_id,
            'snapshot_id': snapshot_id,
            'created': len(fresh.create_ids),
            'updated': len(fresh.update_ids),
            'deleted': len(fresh.delete_ids),
            'discarded_candidates': 0,
        }


def _inspection(validation: UsersReplaceValidation) -> dict[str, object]:
    return {
        'snapshot_id': validation.snapshot.snapshot_id,
        'snapshot_digest': validation.snapshot.content_digest,
        'origin_environment': validation.snapshot.origin_environment,
        'captured_at_utc': validation.snapshot.captured_at_utc,
        'approved_count': len(validation.snapshot.users),
        'create_ids': list(validation.create_ids),
        'update_ids': list(validation.update_ids),
        'delete_ids': list(validation.delete_ids),
        'unchanged_count': (
            len(validation.snapshot.users)
            - len(validation.create_ids)
            - len(validation.update_ids)
        ),
        'differences': [
            {
                'user_id': item.user_id,
                'kind': item.kind.value,
                'fields': list(item.fields),
            }
            for item in validation.differences
        ],
        'target_fingerprint': validation.snapshot.content_digest,
    }


def _required(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise UsersRecoveryConflictError(f'{label} is required')
    return value


def _approval_reference(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UsersRecoveryConflictError('Approval reference is required')
    return value.strip()
