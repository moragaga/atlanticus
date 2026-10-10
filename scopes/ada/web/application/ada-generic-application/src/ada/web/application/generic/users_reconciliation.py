from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from atlanticus.web.users.models import RuntimeUser


class UsersRuntimeReconciliationError(RuntimeError):
    pass


class UsersRuntimeReconciliationChangedError(UsersRuntimeReconciliationError):
    pass


class UsersRuntimeReconciliationIncompleteError(UsersRuntimeReconciliationError):
    pass


class RuntimeReconciliationStore(Protocol):
    def list_users(self) -> tuple[RuntimeUser, ...]: ...

    def replace_all(self, users: tuple[RuntimeUser, ...]) -> tuple[RuntimeUser, ...]: ...


class RuntimeUsersMaterializer(Protocol):
    def materialize_all(self) -> tuple[RuntimeUser, ...]: ...


@dataclass(frozen=True, slots=True)
class UsersRuntimeReconciliationPlan:
    plan_id: str
    creates: tuple[str, ...]
    updates: tuple[str, ...]
    deletes: tuple[str, ...]
    unchanged: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.creates or self.updates or self.deletes)

    @property
    def target_count(self) -> int:
        return len(self.creates) + len(self.updates) + len(self.unchanged)


@dataclass(frozen=True, slots=True)
class UsersRuntimeReconciliationResult:
    plan: UsersRuntimeReconciliationPlan
    actor: str
    persisted_count: int


class AdaUsersRuntimeReconciler:
    def __init__(
        self,
        *,
        materializer: RuntimeUsersMaterializer,
        store: RuntimeReconciliationStore,
    ) -> None:
        self._materializer = materializer
        self._store = store

    def preview(self) -> UsersRuntimeReconciliationPlan:
        plan, _desired = self._capture()
        return plan

    def apply(
        self,
        *,
        expected_plan_id: str,
        actor: str,
        allow_deletes: bool = False,
    ) -> UsersRuntimeReconciliationResult:
        if not isinstance(expected_plan_id, str) or not expected_plan_id.strip():
            raise ValueError('A confirmed Users runtime reconciliation plan is required')
        if (
            not isinstance(actor, str)
            or not actor.strip()
            or actor != actor.strip()
            or len(actor) > 128
            or any(ord(char) < 32 for char in actor)
        ):
            raise ValueError('Users runtime reconciliation actor is invalid')
        if not isinstance(allow_deletes, bool):
            raise TypeError('Users runtime deletion confirmation must be boolean')
        plan, desired = self._capture()
        if plan.plan_id != expected_plan_id:
            raise UsersRuntimeReconciliationChangedError(
                'Users runtime reconciliation changed since the preview'
            )
        if plan.deletes and not allow_deletes:
            raise UsersRuntimeReconciliationError(
                'Users runtime deletion requires explicit confirmation'
            )
        if not plan.has_changes:
            return UsersRuntimeReconciliationResult(
                plan=plan,
                actor=actor,
                persisted_count=len(desired),
            )
        if _unique_sorted(self._materializer.materialize_all()) != desired:
            raise UsersRuntimeReconciliationChangedError(
                'Users runtime source data changed before reconciliation'
            )
        try:
            persisted = self._store.replace_all(desired)
            if tuple(sorted(persisted, key=lambda user: user.user_id)) != desired:
                raise UsersRuntimeReconciliationIncompleteError(
                    'Users runtime replacement returned unexpected data'
                )
            if _unique_sorted(self._store.list_users()) != desired:
                raise UsersRuntimeReconciliationIncompleteError(
                    'Users runtime persistence differs from the expected projection'
                )
            if _unique_sorted(self._materializer.materialize_all()) != desired:
                raise UsersRuntimeReconciliationIncompleteError(
                    'Users runtime sources changed during reconciliation'
                )
        except Exception as error:
            raise UsersRuntimeReconciliationIncompleteError(
                'Users runtime reconciliation did not complete; verify current state before retrying'
            ) from error
        return UsersRuntimeReconciliationResult(
            plan=plan,
            actor=actor,
            persisted_count=len(desired),
        )

    def _capture(self) -> tuple[UsersRuntimeReconciliationPlan, tuple[RuntimeUser, ...]]:
        desired = _unique_sorted(self._materializer.materialize_all())
        current = _unique_sorted(self._store.list_users())
        existing = {user.user_id: user for user in current}
        target = {user.user_id: user for user in desired}
        creates = tuple(sorted(target.keys() - existing.keys()))
        deletes = tuple(sorted(existing.keys() - target.keys()))
        updates = tuple(
            sorted(user_id for user_id in target.keys() & existing.keys() if target[user_id] != existing[user_id])
        )
        unchanged = tuple(
            sorted(user_id for user_id in target.keys() & existing.keys() if target[user_id] == existing[user_id])
        )
        plan_id = _fingerprint(current=current, desired=desired)
        return (
            UsersRuntimeReconciliationPlan(
                plan_id=plan_id,
                creates=creates,
                updates=updates,
                deletes=deletes,
                unchanged=unchanged,
            ),
            desired,
        )


def _unique_sorted(users: Iterable[RuntimeUser]) -> tuple[RuntimeUser, ...]:
    values = tuple(users)
    if any(not isinstance(user, RuntimeUser) for user in values):
        raise TypeError('Users runtime reconciliation requires RuntimeUser entries')
    identifiers = tuple(user.user_id for user in values)
    if len(set(identifiers)) != len(identifiers):
        raise UsersRuntimeReconciliationError('Users runtime reconciliation contains duplicate users')
    return tuple(sorted(values, key=lambda user: user.user_id))


def _fingerprint(
    *,
    current: tuple[RuntimeUser, ...],
    desired: tuple[RuntimeUser, ...],
) -> str:
    payload = {
        'current': [user.to_document() for user in current],
        'desired': [user.to_document() for user in desired],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()
