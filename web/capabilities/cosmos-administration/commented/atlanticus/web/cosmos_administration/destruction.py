from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from atlanticus.connectivity.cosmos import (
    CosmosContainerNotFoundError,
    CosmosPreconditionFailedError,
    CosmosProvisioner,
)
from atlanticus.connectivity.cosmos.destruction import CosmosContainerDeletion
from atlanticus.connectivity.cosmos.inventory import CosmosContainerProperties, CosmosInventory
from atlanticus.web.cosmos_administration.audit import CosmosLifecycleAudit
from atlanticus.web.cosmos_administration.backup import CosmosBackupService
from atlanticus.web.cosmos_administration.lifecycle import (
    CosmosLifecycleConfigurationError,
    CosmosLifecycleService,
    CosmosManagedContainer,
)


# Contrato pedagógico: responsabilidad aislada y reutilizable.
class CosmosDestructiveOperationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
# Contrato pedagógico: responsabilidad aislada y reutilizable.
class CosmosDestructivePreview:
    container: CosmosManagedContainer
    physical: CosmosContainerProperties
    confirmation_target: str


@dataclass(frozen=True, slots=True)
# Contrato pedagógico: responsabilidad aislada y reutilizable.
class CosmosDestructiveReport:
    action: Literal['delete', 'recreate']
    status: Literal['DELETED', 'RECREATED']
    container: CosmosManagedContainer
    action_id: str
    backup_id: str
    operator_id: str
    point_in_time_consistent: bool


# Contrato pedagógico: responsabilidad aislada y reutilizable.
class CosmosDestructiveService:
    # Validación y errores controlados antes de realizar operaciones.
    def __init__(
        self,
        *,
        lifecycle: CosmosLifecycleService,
        backups: CosmosBackupService,
        audit: CosmosLifecycleAudit,
        authenticated_root: Callable[[], str | None],
    ) -> None:
        if not isinstance(lifecycle, CosmosLifecycleService):
            raise CosmosLifecycleConfigurationError('Cosmos lifecycle service is required')
        if not isinstance(backups, CosmosBackupService):
            raise CosmosLifecycleConfigurationError('Cosmos backup service is required')
        if not isinstance(audit, CosmosLifecycleAudit):
            raise CosmosLifecycleConfigurationError('Durable Cosmos lifecycle audit is required')
        if not callable(authenticated_root):
            raise CosmosLifecycleConfigurationError('ROOT principal provider is required')
        self._lifecycle = lifecycle
        self._backups = backups
        self._audit = audit
        self._authenticated_root = authenticated_root

    # Validación y errores controlados antes de realizar operaciones.
    def inspect(self, *, logical_id: str) -> CosmosDestructivePreview:
        container, client = self._lifecycle._resolve(logical_id)
        physical = CosmosInventory(client=client).read_container(container_name=container.spec.name)
        if physical.etag is None:
            raise CosmosDestructiveOperationError('Cosmos container ETag is unavailable')
        return CosmosDestructivePreview(
            container=container,
            physical=physical,
            confirmation_target=(
                f'{container.connection_ref}/{container.database_name}/{container.spec.name}'
            ),
        )

    # Validación y errores controlados antes de realizar operaciones.
    def delete_container(
        self,
        *,
        logical_id: str,
        expected_etag: str,
        confirmation_target: str,
        destination_ref: str,
        backup_id: str,
        acknowledge_data_loss: bool,
    ) -> CosmosDestructiveReport:
        return self._execute(
            action='delete',
            logical_id=logical_id,
            expected_etag=expected_etag,
            confirmation_target=confirmation_target,
            destination_ref=destination_ref,
            backup_id=backup_id,
            acknowledge_data_loss=acknowledge_data_loss,
        )

    # Validación y errores controlados antes de realizar operaciones.
    def recreate_container(
        self,
        *,
        logical_id: str,
        expected_etag: str,
        confirmation_target: str,
        destination_ref: str,
        backup_id: str,
        acknowledge_data_loss: bool,
    ) -> CosmosDestructiveReport:
        return self._execute(
            action='recreate',
            logical_id=logical_id,
            expected_etag=expected_etag,
            confirmation_target=confirmation_target,
            destination_ref=destination_ref,
            backup_id=backup_id,
            acknowledge_data_loss=acknowledge_data_loss,
        )

    # Validación y errores controlados antes de realizar operaciones.
    def _execute(
        self,
        *,
        action: Literal['delete', 'recreate'],
        logical_id: str,
        expected_etag: str,
        confirmation_target: str,
        destination_ref: str,
        backup_id: str,
        acknowledge_data_loss: bool,
    ) -> CosmosDestructiveReport:
        operator_id = self._authenticated_root()
        if not isinstance(operator_id, str) or not operator_id.strip():
            raise CosmosDestructiveOperationError('ROOT authorization is required')
        preview = self.inspect(logical_id=logical_id)
        if not isinstance(expected_etag, str) or preview.physical.etag != expected_etag:
            raise CosmosPreconditionFailedError('Cosmos container changed after inspection')
        if confirmation_target != preview.confirmation_target:
            raise CosmosDestructiveOperationError('Cosmos deletion target was not confirmed')
        if acknowledge_data_loss is not True:
            raise CosmosDestructiveOperationError('Explicit data loss acknowledgement is required')
        backup = self._backups.verify_backup(destination_ref=destination_ref, backup_id=backup_id)
        target = preview.container
        if (
            not backup.verified
            or backup.connection_ref != target.connection_ref
            or backup.database_name != target.database_name
            or backup.container_name != target.spec.name
        ):
            raise CosmosDestructiveOperationError('Verified backup does not match Cosmos target')
        action_id = uuid.uuid4().hex
        common = {
            'action_id': action_id,
            'action': action,
            'operator_id': operator_id,
            'connection_ref': target.connection_ref,
            'database_name': target.database_name,
            'container_name': target.spec.name,
            'logical_id': target.logical_id,
            'backup_id': backup.backup_id,
            'destination_ref': backup.destination_ref,
            'expected_etag': expected_etag,
            'acknowledged_data_loss': True,
            'point_in_time_consistent': backup.point_in_time_consistent,
        }
        self._audit.record(
            action_id=action_id,
            stage='intent',
            payload={**common, 'stage': 'intent', 'at_utc': _utc_now()},
        )
        _, client = self._lifecycle._resolve(logical_id)
        deleted = False
        try:
            CosmosContainerDeletion(client=client).delete_container(
                container_name=target.spec.name, expected_etag=expected_etag
            )
            deleted = True
            try:
                CosmosInventory(client=client).read_container(container_name=target.spec.name)
            except CosmosContainerNotFoundError:
                pass
            else:
                raise CosmosDestructiveOperationError('Cosmos container remains after deletion')
            if action == 'recreate':
                provisioner = CosmosProvisioner(client=client)
                created = provisioner.ensure_containers((target.spec,))
                if created != (target.spec.name,):
                    raise CosmosDestructiveOperationError('Cosmos container was not recreated')
                provisioner.validate_containers((target.spec,))
        except Exception as error:
            with contextlib.suppress(Exception):
                self._audit.record(
                    action_id=action_id,
                    stage='failed',
                    payload={
                        **common,
                        'stage': 'failed',
                        'at_utc': _utc_now(),
                        'physical_deletion_completed': deleted,
                        'error_type': type(error).__name__,
                    },
                )
            raise
        self._audit.record(
            action_id=action_id,
            stage='completed',
            payload={**common, 'stage': 'completed', 'at_utc': _utc_now()},
        )
        return CosmosDestructiveReport(
            action=action,
            status='RECREATED' if action == 'recreate' else 'DELETED',
            container=target,
            action_id=action_id,
            backup_id=backup.backup_id,
            operator_id=operator_id,
            point_in_time_consistent=backup.point_in_time_consistent,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
