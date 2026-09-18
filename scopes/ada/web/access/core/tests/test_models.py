import pytest

from ada.web.access.errors import AdaAccessDefinitionError
from ada.web.access.models import (
    EffectiveAdaAccess,
    ProfileAccessGrant,
    UserProfileAssignment,
    normalize_access_key,
)


def test_user_profile_assignment_normalizes_user_and_profiles() -> None:
    assignment = UserProfileAssignment(
        user_id='  user-1  ',
        profile_keys=('Operator', 'Viewer'),
    )

    assert assignment.user_id == 'user-1'
    assert assignment.profile_keys == ('operator', 'viewer')


def test_user_profile_assignment_rejects_duplicate_profiles() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='unique'):
        UserProfileAssignment(user_id='user-1', profile_keys=('operator', 'OPERATOR'))


def test_profile_access_grant_normalizes_access_keys() -> None:
    grant = ProfileAccessGrant(
        profile_key='Operator',
        access_keys=('Navigation.View', 'KPIS.Manage'),
    )

    assert grant.profile_key == 'operator'
    assert grant.access_keys == ('navigation.view', 'kpis.manage')


def test_access_key_rejects_invalid_format() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='invalid format'):
        normalize_access_key('navigation view')


def test_effective_access_rejects_duplicate_access_keys() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='unique'):
        EffectiveAdaAccess(
            user_id='user-1',
            profile_keys=('operator',),
            access_keys=('navigation.view', 'NAVIGATION.VIEW'),
        )
