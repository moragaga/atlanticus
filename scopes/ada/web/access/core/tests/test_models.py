import pytest

from ada.web.access.errors import AdaAccessDefinitionError
from ada.web.access.models import EffectiveAdaAccess, ProfileAccessGrant, normalize_access_key


def test_profile_access_grant_normalizes_profile_and_access_keys() -> None:
    grant = ProfileAccessGrant(
        profile_key='Operator',
        access_keys=('Navigation.View', 'KPIS.Manage'),
    )

    assert grant.profile_key == 'operator'
    assert grant.access_keys == ('navigation.view', 'kpis.manage')


def test_access_key_rejects_invalid_format() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='invalid format'):
        normalize_access_key('navigation view')


def test_profile_access_grant_rejects_duplicate_access_keys() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='unique'):
        ProfileAccessGrant(
            profile_key='operator',
            access_keys=('navigation.view', 'NAVIGATION.VIEW'),
        )


def test_effective_access_contains_one_profile_and_unique_access_keys() -> None:
    effective = EffectiveAdaAccess(
        profile_key='Analyst',
        access_keys=('alarms.view', 'reports.view'),
    )

    assert effective.profile_key == 'analyst'
    assert effective.access_keys == ('alarms.view', 'reports.view')


def test_effective_access_rejects_duplicate_access_keys() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='unique'):
        EffectiveAdaAccess(
            profile_key='operator',
            access_keys=('navigation.view', 'NAVIGATION.VIEW'),
        )
