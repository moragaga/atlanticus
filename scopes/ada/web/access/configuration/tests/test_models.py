import pytest

from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.errors import AdaAccessDefinitionError
from ada.web.access.models import ProfileAccessGrant, UserProfileAssignment
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition


def _profiles() -> ProfileCatalog:
    return ProfileCatalog(
        profiles=(
            ProfileDefinition(
                key='operator',
                label='Operator',
                background_color='#123456',
            ),
            ProfileDefinition(
                key='viewer',
                label='Viewer',
                background_color='#654321',
            ),
        )
    )


def _configuration() -> AdaAccessConfiguration:
    return AdaAccessConfiguration(
        user_profiles=(
            UserProfileAssignment(
                user_id='user-1',
                profile_keys=('operator', 'viewer'),
            ),
        ),
        profile_access=(
            ProfileAccessGrant(
                profile_key='operator',
                access_keys=('navigation.view', 'kpis.manage'),
            ),
            ProfileAccessGrant(
                profile_key='viewer',
                access_keys=('navigation.view',),
            ),
        ),
    )


def test_configuration_round_trips_document() -> None:
    configuration = _configuration()

    assert AdaAccessConfiguration.from_document(configuration.to_document()) == configuration


def test_configuration_rejects_duplicate_user_assignments() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='assignments must be unique'):
        AdaAccessConfiguration(
            user_profiles=(
                UserProfileAssignment(user_id='user-1'),
                UserProfileAssignment(user_id='user-1'),
            )
        )


def test_configuration_validates_profile_references() -> None:
    configuration = AdaAccessConfiguration(
        user_profiles=(UserProfileAssignment(user_id='user-1', profile_keys=('missing',)),)
    )

    with pytest.raises(ValueError, match='Unknown profile'):
        configuration.validate_profiles(_profiles())


def test_configuration_resolves_effective_access_from_assigned_profiles() -> None:
    effective = _configuration().resolve('user-1', profiles=_profiles())

    assert effective.user_id == 'user-1'
    assert effective.profile_keys == ('operator', 'viewer')
    assert effective.access_keys == ('navigation.view', 'kpis.manage')


def test_configuration_accepts_configured_administrator_profile() -> None:
    profiles = ProfileCatalog(
        profiles=(
            ProfileDefinition(
                key='administrator',
                label='Administrator',
                background_color='#112233',
            ),
        )
    )
    configuration = AdaAccessConfiguration(
        user_profiles=(
            UserProfileAssignment(user_id='user-1', profile_keys=('administrator',)),
        ),
        profile_access=(
            ProfileAccessGrant(
                profile_key='administrator',
                access_keys=('kpis.manage',),
            ),
        ),
    )

    configuration.validate_profiles(profiles)
    effective = configuration.resolve('user-1', profiles=profiles)

    assert effective.profile_keys == ('administrator',)
    assert effective.access_keys == ('kpis.manage',)


def test_configuration_resolves_unassigned_user_without_profiles_or_access() -> None:
    effective = _configuration().resolve('user-2', profiles=_profiles())

    assert effective.user_id == 'user-2'
    assert effective.profile_keys == ()
    assert effective.access_keys == ()
