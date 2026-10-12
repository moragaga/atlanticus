from __future__ import annotations

from dataclasses import dataclass

from flask import has_request_context

from atlanticus.web.identity.access import AccessRuntime, AccessStatus
from atlanticus.web.identity.errors import AccessContextError
from atlanticus.web.users.errors import UsersContextError
from atlanticus.web.users.runtime import UsersRuntime

ALARM_SURFACE_VIEW = 'alarm.surface_view'
ALARM_ACTION_INFORMATION = 'alarm.action_information'
ALARM_ACTION_MANAGEMENT = 'alarm.action_management'
ALARM_MANAGEMENT_SUMMARY_VIEW = 'alarm.management_summary_view'
ALARM_STATUS_VIEW = 'alarm.status_view'
ALARM_ACCESS_KEYS = frozenset({
    ALARM_SURFACE_VIEW,
    ALARM_ACTION_INFORMATION,
    ALARM_ACTION_MANAGEMENT,
    ALARM_MANAGEMENT_SUMMARY_VIEW,
    ALARM_STATUS_VIEW,
})


@dataclass(frozen=True, slots=True)
class AlarmAccessBinding:
    access_runtime: AccessRuntime
    users_runtime: UsersRuntime

    def __post_init__(self) -> None:
        if not isinstance(self.access_runtime, AccessRuntime):
            raise TypeError('Alarm access requires AccessRuntime')
        if not isinstance(self.users_runtime, UsersRuntime):
            raise TypeError('Alarm access requires UsersRuntime')

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
            if (
                user is None or not user.enabled
                or (access.user_id is not None and access.user_id != user.user_id)
                or access.identity.issuer != user.issuer
                or access.identity.subject_id != user.subject_id
            ):
                return False
            return user.has_full_access or key in user.access_keys
        except (AccessContextError, UsersContextError):
            return False


def deny_alarm_access(_key: str) -> bool:
    return False
