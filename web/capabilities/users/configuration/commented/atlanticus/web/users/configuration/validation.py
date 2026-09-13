from __future__ import annotations

# Esta capa concentra la validación reusable que comparten el workflow legacy y la proyección canónica exact-release.

from dataclasses import dataclass
from typing import Literal

from atlanticus.web.users.configuration.models import UsersConfigurationCatalog

IssueLevel = Literal['error', 'warning']


@dataclass(frozen=True, slots=True)
class UsersProjectionIssue:
    code: str
    message: str
    level: IssueLevel = 'error'
    path: str | None = None


def validate_users_projection_catalog(
    catalog: UsersConfigurationCatalog,
) -> tuple[UsersProjectionIssue, ...]:
    issues: list[UsersProjectionIssue] = []
    profile_keys = {profile.key for profile in catalog.profile_catalog().all()}
    for index, user in enumerate(catalog.users):
        if user.profile_key not in profile_keys:
            issues.append(
                UsersProjectionIssue(
                    code='user.profile.invalid',
                    message='User profile does not exist',
                    path=f'users[{index}].profile_key',
                )
            )
    return tuple(issues)
