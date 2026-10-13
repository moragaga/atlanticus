from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from flask import has_request_context

from atlanticus.web.identity.access import AccessRuntime, AccessSnapshot, AccessStatus
from atlanticus.web.identity.errors import AccessContextError
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.profiles.models import GUEST_PROFILE_KEY
from atlanticus.web.users.errors import UsersContextError
from atlanticus.web.users.runtime import UsersRuntime

ALARM_SURFACE_VIEW = 'alarm.surface_view'
ALARM_CARDS_VIEW = 'alarm.cards_view'
ALARM_ACTION_INFORMATION = 'alarm.action_information'
ALARM_ACTION_MANAGEMENT = 'alarm.action_management'
ALARM_MANAGEMENT_SUMMARY_VIEW = 'alarm.management_summary_view'
ALARM_STATUS_VIEW = 'alarm.status_view'
ALARM_ACCESS_KEYS = frozenset({
    ALARM_SURFACE_VIEW,
    ALARM_CARDS_VIEW,
    ALARM_ACTION_INFORMATION,
    ALARM_ACTION_MANAGEMENT,
    ALARM_MANAGEMENT_SUMMARY_VIEW,
    ALARM_STATUS_VIEW,
})


@dataclass(frozen=True, slots=True)
class AlarmAccessBinding:
    access_runtime: AccessRuntime
    users_runtime: UsersRuntime
    trusted_local_principal: Callable[[], ManagerPrincipal] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.access_runtime, AccessRuntime):
            raise TypeError('Alarm access requires AccessRuntime')
        if not isinstance(self.users_runtime, UsersRuntime):
            raise TypeError('Alarm access requires UsersRuntime')
        if self.trusted_local_principal is not None and not callable(self.trusted_local_principal):
            raise TypeError('Trusted local principal must be callable')

    def allows(self, key: str) -> bool:
        if key not in ALARM_ACCESS_KEYS:
            raise ValueError('Alarm access key is unknown')
        if not has_request_context():
            return False
        try:
            access = self.access_runtime.current_or_none()
            if access is None or access.status is not AccessStatus.READY or access.identity is None:
                return False
            if access.bootstrap_root:
                return True
            user = self.users_runtime.current_or_none(access)
            if user is None:
                return self._allows_trusted_local(access)
            if (
                not user.enabled
                or (access.user_id is not None and access.user_id != user.user_id)
                or access.identity.issuer != user.issuer
                or access.identity.subject_id != user.subject_id
            ):
                return False
            if user.has_full_access or key in user.access_keys:
                return True
            return user.profile.id == GUEST_PROFILE_KEY and self._allows_trusted_local(access)
        except (AccessContextError, UsersContextError):
            return False

    def _allows_trusted_local(self, access: AccessSnapshot) -> bool:
        if self.trusted_local_principal is None:
            return False
        try:
            principal = self.trusted_local_principal()
        except (AccessContextError, UsersContextError, ValueError):
            return False
        return (
            isinstance(principal, ManagerPrincipal)
            and principal.is_local
            and principal.administrative_override
            and access.identity is not None
            and principal.subject_id == access.identity.subject_id
        )


def can_view_alarm_cards(allows: Callable[[str], bool]) -> bool:
    return allows(ALARM_SURFACE_VIEW) and allows(ALARM_CARDS_VIEW)


def deny_alarm_access(_key: str) -> bool:
    return False
