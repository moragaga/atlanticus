from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from uuid import uuid4

from ada.web.application.configuration_manager.wiring import ADA_ACCESS_SOURCE_KEY
from ada.web.application.generic.manager_deployment import (
    DurableManagerConfiguration,
    DurableManagerRuntime,
    ManagerStartupOptions,
    open_durable_manager,
    resolve_durable_manager_configuration,
)
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.blob.recovery import (
    BlobApprovedUsersSnapshotStore,
    BlobUsersRecoveryAuditStore,
)
from atlanticus.web.users.recovery import (
    UsersApprovedRecoveryService,
    UsersRecoveryConflictError,
    UsersRecoveryValidation,
)


# Los cuatro comandos comparten contexto explícito del ambiente y del directorio declarado.
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Operate approved Users recovery snapshots')
    actions = parser.add_subparsers(dest='action', required=True)
    for action in ('preview', 'capture', 'validate', 'restore'):
        command = actions.add_parser(action)
        command.add_argument('--identity-realm', required=True)
        command.add_argument('--environment', required=True)
        if action in {'validate', 'restore'}:
            command.add_argument('--snapshot-id', required=True)
        if action in {'capture', 'restore'}:
            command.add_argument('--expected-digest', required=True)
            command.add_argument('--operator-id', required=True)
            command.add_argument('--approval-reference', required=True)
        if action == 'capture':
            command.add_argument('--confirm-capture', action='store_true')
        if action == 'restore':
            command.add_argument('--confirm-restore', action='store_true')
            command.add_argument('--confirm-maintenance', action='store_true')
            command.add_argument('--reviewed-revocations', action='store_true')
    return parser


# Se imprime JSON estable sin nombres, correos ni contenido de credenciales.
def _output(document: dict[str, object]) -> None:
    print(json.dumps(document, ensure_ascii=False, sort_keys=True))


# La validación presenta discrepancias sin escribir en el destino.
def _validation_document(validation: UsersRecoveryValidation) -> dict[str, object]:
    return {
        'snapshot_id': validation.snapshot.snapshot_id,
        'snapshot_digest': validation.snapshot.content_digest,
        'origin_environment': validation.snapshot.origin_environment,
        'registry_state': validation.registry_state.value,
        'can_restore': validation.can_restore,
        'registry_conflict_user_ids': list(validation.registry_conflict_user_ids),
        'differences': [
            {'user_id': item.user_id, 'kind': item.kind.value, 'fields': list(item.fields)}
            for item in validation.differences
        ],
    }


# La composición específica de ADA reutiliza los stores y las conexiones existentes.
# La lógica reutilizable permanece en Atlanticus y no conoce este adaptador.
def _service(
    *,
    resolved: DurableManagerConfiguration,
    deployment: DurableManagerRuntime,
    identity_realm: str,
    environment: str,
) -> UsersApprovedRecoveryService:
    resource = deployment.resources.users_registry
    client = deployment.connections.storage[resource.connection_ref]
    namespace = resolved.namespace

    # No se permiten perfiles predeterminados implícitos si falta la proyección.
    def profiles_provider() -> ProfileCatalog:
        active = deployment.stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY)
        if active is None or not isinstance(active.payload, ProfileCatalog):
            raise UsersRecoveryConflictError('An active Profiles projection is required')
        return active.payload

    return UsersApprovedRecoveryService(
        registry=deployment.stores.users_registry,
        promoted=deployment.stores.users_promoted,
        profiles=profiles_provider,
        snapshots=BlobApprovedUsersSnapshotStore(
            client=client,
            container_name=resource.container_name,
            prefix=namespace.application_blob_name('users/recovery/snapshots'),
        ),
        audit=BlobUsersRecoveryAuditStore(
            client=client,
            container_name=resource.container_name,
            prefix=namespace.application_blob_name('users/recovery/audit'),
        ),
        application_key=namespace.application_namespace,
        identity_realm=identity_realm,
        environment=environment,
    )


# Los requisitos de confirmación se comprueban antes de abrir conexiones.
def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == 'capture' and not args.confirm_capture:
        raise UsersRecoveryConflictError('Explicit capture confirmation is required')
    if args.action == 'restore' and not (
        args.confirm_restore and args.confirm_maintenance and args.reviewed_revocations
    ):
        raise UsersRecoveryConflictError(
            'Restore requires confirmation, maintenance and revocation review'
        )
    settings = AdaGenericSettings()
    # No se expone una restauración productiva sin identidad operacional autenticada.
    if not settings.environment.is_local:
        raise UsersRecoveryConflictError(
            'This recovery operator is restricted to local environments'
        )
    if ManagerStartupOptions().provider != 'durable':
        raise UsersRecoveryConflictError('Durable Manager must be explicitly enabled')
    resolved = resolve_durable_manager_configuration(settings)
    with open_durable_manager(settings) as deployment:
        service = _service(
            resolved=resolved,
            deployment=deployment,
            identity_realm=args.identity_realm,
            environment=args.environment,
        )
        # Preview y capture usan el mismo conjunto aprobado y huella portable.
        if args.action == 'preview':
            preview = service.preview_capture()
            _output(
                {
                    'registry_version': preview.registry_version,
                    'snapshot_digest': preview.content_digest,
                    'approved_user_ids': [user.user_id for user in preview.approved_users],
                    'approved_users': [user.to_document() for user in preview.approved_users],
                    'candidate_user_ids': list(preview.candidate_user_ids),
                }
            )
            return 0
        if args.action == 'capture':
            preview = service.preview_capture()
            if preview.content_digest != args.expected_digest:
                raise UsersRecoveryConflictError('Approved Users preview digest changed')
            snapshot = service.capture(
                preview=preview,
                approved_user_ids=tuple(user.user_id for user in preview.approved_users),
                operator_id=args.operator_id,
                approval_reference=args.approval_reference,
                confirmed=True,
            )
            _output(
                {
                    'snapshot_id': snapshot.snapshot_id,
                    'snapshot_digest': snapshot.content_digest,
                    'origin_environment': snapshot.origin_environment,
                    'approved_count': len(snapshot.users),
                }
            )
            return 0
        if args.action == 'validate':
            _output(_validation_document(service.validate(args.snapshot_id)))
            return 0
        # Una recuperación de Users no debe fingir que recupera Access.
        if deployment.stores.access.get_active(ADA_ACCESS_SOURCE_KEY) is None:
            raise UsersRecoveryConflictError('An active Access projection is required')
        validation = service.validate(args.snapshot_id)
        if not validation.can_restore:
            raise UsersRecoveryConflictError('Target is not empty or prepared for restore')
        if validation.snapshot.content_digest != args.expected_digest:
            raise UsersRecoveryConflictError('Approved Users snapshot digest does not match')
        # Cada ejecución necesita un identificador propio para su auditoría.
        operation_id = uuid4().hex
        _output({'stage': 'starting', 'operation_id': operation_id})
        after = service.restore(
            validation=validation,
            confirmed_digest=args.expected_digest,
            operator_id=args.operator_id,
            approval_reference=args.approval_reference,
            operation_id=operation_id,
            confirmed=True,
            maintenance_confirmed=True,
        )
        _output({'stage': 'completed', 'operation_id': operation_id, **_validation_document(after)})
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
