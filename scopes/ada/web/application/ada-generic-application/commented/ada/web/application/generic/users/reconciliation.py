from __future__ import annotations

from dataclasses import replace

from ada.web.application.generic.users.materialization import AdaUsersRuntimeMaterializer
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import GUEST_PROFILE_KEY
from atlanticus.web.users.errors import UsersIdentityConflictError
from atlanticus.web.users.models import RuntimeUser
from atlanticus.web.users.reconstruction import (
    UsersReconstructionConflictError,
    UsersReconstructionPreview,
)
from atlanticus.web.users.store import UsersRuntimeStore


# Reconcilia el RuntimeUser completo desde las autoridades de ADA, no desde snapshots de runtime.
class AdaUsersReconciliationWorkflow:
    def __init__(
        self, *, materializer: AdaUsersRuntimeMaterializer, runtime: UsersRuntimeStore
    ) -> None:
        self._materializer = materializer
        self._runtime = runtime

    # La inspección no escribe datos; detecta diferencias y bajas lógicas.
    def inspect(self) -> UsersReconstructionPreview:
        desired = tuple(sorted(self._materializer.materialize_all(), key=lambda user: user.user_id))
        if len({user.user_id for user in desired}) != len(desired):
            raise UsersReconstructionConflictError('Users reconciliation contains duplicate identities')
        runtime_users = self._runtime.list_users()
        existing = {user.user_id: user for user in runtime_users}
        if len(existing) != len(runtime_users):
            raise UsersReconstructionConflictError('Users runtime contains duplicate identities')
        desired_ids = {user.user_id for user in desired}
        return UsersReconstructionPreview(
            desired_users=desired,
            create_ids=tuple(user.user_id for user in desired if user.user_id not in existing),
            update_ids=tuple(
                user.user_id for user in desired
                if user.user_id in existing and existing[user.user_id] != user
            ),
            disable_ids=tuple(sorted(
                user.user_id for user in existing.values()
                if user.user_id not in desired_ids
                and not user.is_local
                and user.profile.id != GUEST_PROFILE_KEY
                and (user.enabled or user.access_keys)
            )),
        )

    # La confirmación vuelve a inspeccionar, publica por usuario y comprueba la convergencia.
    def apply(self, preview: UsersReconstructionPreview) -> UsersReconstructionPreview:
        if not isinstance(preview, UsersReconstructionPreview):
            raise TypeError('ADA users reconciliation preview is required')
        if self.inspect() != preview:
            raise UsersReconstructionConflictError('ADA users reconciliation sources changed')
        existing = {user.user_id: user for user in self._runtime.list_users()}
        desired = {user.user_id: user for user in preview.desired_users}
        for user_id in preview.disable_ids:
            previous = existing[user_id]
            self._publish(replace(previous, enabled=False, access_keys=()), previous)
        for user_id in (*preview.create_ids, *preview.update_ids):
            self._publish(desired[user_id], existing.get(user_id))
        after = self.inspect()
        if after.has_changes:
            raise UsersReconstructionConflictError('ADA users reconciliation is incomplete')
        return after

    def publish_one(self, user_id: str) -> RuntimeUser:
        desired = self._materializer.materialize_user(user_id)
        current = self._resolve(desired)
        return self._publish(desired, current)

    # Protege cambios concurrentes visibles y evita borrar una asignación operacional sin prueba.
    def _publish(self, desired: RuntimeUser, expected: RuntimeUser | None) -> RuntimeUser:
        current = self._resolve(desired)
        if current != expected:
            raise UsersReconstructionConflictError('ADA runtime user changed during reconciliation')
        if (
            current is not None
            and current.operational != desired.operational
            and desired.operational.area is None
            and desired.operational.position is None
            and desired.operational.group is None
            and desired.enabled
        ):
            raise UsersReconstructionConflictError(
                'Existing operational assignment cannot be cleared by reconciliation'
            )
        publish = getattr(self._runtime, 'upsert_user_if_current', None)
        if not callable(publish):
            raise UsersReconstructionConflictError('Runtime store lacks conditional publication')
        try:
            published = publish(desired, expected=expected)
        except UsersIdentityConflictError as error:
            raise UsersReconstructionConflictError('ADA runtime user changed during reconciliation') from error
        persisted = self._resolve(desired)
        if published != desired or persisted != desired:
            raise UsersReconstructionConflictError('ADA reconciled runtime differs from source')
        return persisted

    def _resolve(self, user: RuntimeUser) -> RuntimeUser | None:
        return self._runtime.resolve(
            AuthenticatedIdentity(
                provider_key='ada-reconciliation',
                issuer=user.issuer,
                subject_id=user.subject_id,
            )
        )
