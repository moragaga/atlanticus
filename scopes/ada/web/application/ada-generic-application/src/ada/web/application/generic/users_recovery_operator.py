from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from ada.web.application.generic.manager_deployment import (
    ManagerStartupOptions,
    open_durable_manager,
)
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.users.recovery import ToolUsersRecoveryService, UsersRecoveryConflictError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Operate Tool users-runtime recovery snapshots')
    actions = parser.add_subparsers(dest='action', required=True)
    for action in ('preview', 'capture', 'validate', 'replace'):
        command = actions.add_parser(action)
        if action in {'validate', 'replace'}:
            command.add_argument('--snapshot-id', required=True)
        if action in {'capture', 'replace'}:
            command.add_argument('--operator-id', required=True)
            command.add_argument('--approval-reference', required=True)
        if action == 'capture':
            command.add_argument('--expected-digest', required=True)
            command.add_argument('--confirm-capture', action='store_true')
        if action == 'replace':
            command.add_argument('--confirm-replace', action='store_true')
            command.add_argument('--confirm-maintenance', action='store_true')
            command.add_argument('--reviewed-revocations', action='store_true')
    return parser


def _output(document: dict[str, object]) -> None:
    print(json.dumps(document, ensure_ascii=False, sort_keys=True))


def _service(deployment) -> ToolUsersRecoveryService:
    recovery = deployment.stores.users_recovery
    if recovery is None:
        raise UsersRecoveryConflictError('Users recovery is not configured')
    service = recovery() if callable(recovery) else recovery
    if not isinstance(service, ToolUsersRecoveryService):
        raise UsersRecoveryConflictError('Users recovery service has an invalid type')
    return service


def _validation_document(validation) -> dict[str, object]:
    return {
        'snapshot_id': validation.snapshot.snapshot_id,
        'snapshot_digest': validation.snapshot.content_digest,
        'origin_environment': validation.snapshot.origin_environment,
        'create_user_ids': list(validation.create_ids),
        'update_user_ids': list(validation.update_ids),
        'delete_user_ids': list(validation.delete_ids),
        'differences': [
            {
                'user_id': item.user_id,
                'kind': item.kind.value,
                'fields': list(item.fields),
            }
            for item in validation.differences
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == 'capture' and not args.confirm_capture:
        raise UsersRecoveryConflictError('Explicit capture confirmation is required')
    if args.action == 'replace' and not (
        args.confirm_replace and args.confirm_maintenance and args.reviewed_revocations
    ):
        raise UsersRecoveryConflictError(
            'Replacement requires confirmation, maintenance and revocation review'
        )

    settings = AdaGenericSettings()
    if not settings.environment.is_local:
        raise UsersRecoveryConflictError(
            'This recovery operator is restricted to local environments'
        )
    if ManagerStartupOptions().provider != 'durable':
        raise UsersRecoveryConflictError('Durable Manager must be explicitly enabled')

    with open_durable_manager(settings) as deployment:
        service = _service(deployment)

        if args.action == 'preview':
            preview = service.preview_capture()
            _output(
                {
                    'snapshot_digest': preview.content_digest,
                    'runtime_user_ids': [user.user_id for user in preview.users],
                    'runtime_users': [user.to_document() for user in preview.users],
                }
            )
            return 0

        if args.action == 'capture':
            preview = service.preview_capture()
            if preview.content_digest != args.expected_digest:
                raise UsersRecoveryConflictError('Users runtime preview digest changed')
            snapshot = service.capture(
                preview=preview,
                approved_user_ids=tuple(user.user_id for user in preview.users),
                operator_id=args.operator_id,
                approval_reference=args.approval_reference,
                confirmed=True,
            )
            _output(
                {
                    'snapshot_id': snapshot.snapshot_id,
                    'snapshot_digest': snapshot.content_digest,
                    'origin_environment': snapshot.origin_environment,
                    'runtime_user_count': len(snapshot.users),
                }
            )
            return 0

        if args.action == 'validate':
            _output(_validation_document(service.validate_replace(args.snapshot_id)))
            return 0

        validation = service.validate_replace(args.snapshot_id)
        _output(
            {
                'stage': 'starting',
                'mode': 'replace',
                **_validation_document(validation),
            }
        )
        after = service.replace_snapshot(
            snapshot_id=args.snapshot_id,
            operator_id=args.operator_id,
            approval_reference=args.approval_reference,
            confirmed=True,
            maintenance_confirmed=True,
            revocations_reviewed=True,
        )
        _output(
            {
                'stage': 'completed',
                'mode': 'replace',
                **_validation_document(after),
            }
        )
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
