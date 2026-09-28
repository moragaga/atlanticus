from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from atlanticus.web.users.recovery import (
    UsersApprovedRecoveryService,
    UsersRecoveryConflictError,
    UsersReplaceValidation,
)


@dataclass(frozen=True, slots=True)
class UsersProjectionWorkflow:
    recovery: UsersApprovedRecoveryService | Callable[[], UsersApprovedRecoveryService]
    snapshot_ids: Callable[[], tuple[str, ...]]
    operator_id: Callable[[], str]

    def _service(self) -> UsersApprovedRecoveryService:
        return self.recovery() if callable(self.recovery) else self.recovery

    def history(self) -> tuple[str, ...]:
        return self.snapshot_ids()

    def preview_capture(self) -> dict[str, object]:
        preview = self._service().preview_capture()
        return _capture_document(preview)

    def capture(self, preview: dict[str, object], approval_reference: str) -> dict[str, object]:
        reference = _required(approval_reference, 'Approval reference')
        service = self._service()
        fresh = service.preview_capture()
        if preview != _capture_document(fresh):
            raise UsersRecoveryConflictError('Capture preview changed; review the current state')
        result = service.capture(
            preview=fresh,
            approved_user_ids=tuple(preview['approved_ids']),
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
        validation = self._service().validate_replace(_required(snapshot_id, 'Snapshot id'))
        return _inspection(validation)

    def apply(
        self,
        *,
        inspection: dict[str, object],
        mode: str,
        approval_reference: str,
        maintenance_confirmed: bool,
        revocations_reviewed: bool,
        confirmed: bool,
    ) -> dict[str, object]:
        if not isinstance(inspection, dict):
            raise UsersRecoveryConflictError('Inspect a snapshot before applying changes')
        if mode not in {'restore', 'replace'} or confirmed is not True:
            raise UsersRecoveryConflictError('Explicit operation confirmation is required')
        if maintenance_confirmed is not True or revocations_reviewed is not True:
            raise UsersRecoveryConflictError('Maintenance and revocation review are required')
        reference = _required(approval_reference, 'Approval reference')
        snapshot_id = _required(inspection.get('snapshot_id'), 'Snapshot id')
        service = self._service()
        fresh = service.validate_replace(snapshot_id)
        if inspection != _inspection(fresh):
            raise UsersRecoveryConflictError('Target changed; inspect the snapshot again')
        plan = fresh.plan
        if not (plan.create_ids or plan.update_ids or plan.delete_ids or plan.registry_write_required):
            raise UsersRecoveryConflictError('Users are already aligned with the snapshot')
        operator = _required(self.operator_id(), 'Operator id')
        operation_id = uuid4().hex
        if mode == 'restore':
            if not fresh.recovery.can_restore:
                raise UsersRecoveryConflictError('Strict restore is not available for these differences')
            after = service.restore(
                validation=fresh.recovery,
                confirmed_digest=fresh.recovery.snapshot.content_digest,
                operator_id=operator,
                approval_reference=reference,
                operation_id=operation_id,
                confirmed=True,
                maintenance_confirmed=True,
            )
            if after.differences or after.registry_state.value != 'match':
                raise UsersRecoveryConflictError('Strict restore did not align the target')
        else:
            if not fresh.can_replace:
                raise UsersRecoveryConflictError('REPLACE is blocked by identity or profile conflicts')
            after_replace = service.replace_approved(
                validation=fresh,
                confirmed_digest=fresh.recovery.snapshot.content_digest,
                operator_id=operator,
                approval_reference=reference,
                operation_id=operation_id,
                confirmed=True,
                maintenance_confirmed=True,
                revocations_reviewed=True,
            )
            if (
                after_replace.recovery.differences
                or after_replace.recovery.registry_state.value != 'match'
            ):
                raise UsersRecoveryConflictError('REPLACE did not align the target')
        return {
            'operation_id': operation_id,
            'mode': mode,
            'snapshot_id': snapshot_id,
            'created': len(plan.create_ids),
            'updated': len(plan.update_ids) if mode == 'replace' else 0,
            'deleted': len(plan.delete_ids) if mode == 'replace' else 0,
            'discarded_candidates': len(plan.registry_discarded_ids) if mode == 'replace' else 0,
        }


def _inspection(validation: UsersReplaceValidation) -> dict[str, object]:
    recovery = validation.recovery
    plan = validation.plan
    return {
        'snapshot_id': recovery.snapshot.snapshot_id,
        'snapshot_digest': recovery.snapshot.content_digest,
        'origin_environment': recovery.snapshot.origin_environment,
        'captured_at_utc': recovery.snapshot.captured_at_utc,
        'approved_count': len(recovery.snapshot.users),
        'registry_version': recovery.registry_version,
        'registry_state': recovery.registry_state.value,
        'registry_conflict_ids': list(recovery.registry_conflict_user_ids),
        'can_restore': recovery.can_restore,
        'can_replace': validation.can_replace,
        'create_ids': list(plan.create_ids),
        'update_ids': list(plan.update_ids),
        'delete_ids': list(plan.delete_ids),
        'unchanged_count': len(plan.unchanged_ids),
        'discarded_candidate_ids': list(plan.registry_discarded_ids),
        'registry_write_required': plan.registry_write_required,
        'differences': [
            {'user_id': item.user_id, 'kind': item.kind.value, 'fields': list(item.fields)}
            for item in recovery.differences
        ],
        'target_fingerprint': _target_fingerprint(validation),
    }


def _required(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise UsersRecoveryConflictError(f'{label} is required')
    return value


def _capture_document(preview: object) -> dict[str, object]:
    return {
        'digest': preview.content_digest,
        'registry_version': preview.registry_version,
        'approved_ids': [user.user_id for user in preview.approved_users],
        'candidate_ids': list(preview.candidate_user_ids),
    }


def _target_fingerprint(validation: UsersReplaceValidation) -> str:
    content = {
        'registry_version': validation.recovery.registry_version,
        'users': [
            (item.user.user_id, item.version, item.user.to_document())
            for item in validation.versioned_users
        ],
    }
    encoded = json.dumps(content, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()
