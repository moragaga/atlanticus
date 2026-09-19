import pytest

from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.errors import AdaAccessDefinitionError
from ada.web.access.models import ProfileAccessGrant
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


def test_configuration_round_trips_profile_access_document() -> None:
    configuration = _configuration()
    document = configuration.to_document()

    assert set(document) == {'profile_access'}
    assert AdaAccessConfiguration.from_document(document) == configuration


def test_configuration_rejects_duplicate_profile_grants() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='profile grants must be unique'):
        AdaAccessConfiguration(
            profile_access=(
                ProfileAccessGrant(profile_key='operator'),
                ProfileAccessGrant(profile_key='OPERATOR'),
            )
        )


def test_configuration_validates_profile_references() -> None:
    configuration = AdaAccessConfiguration(
        profile_access=(
            ProfileAccessGrant(
                profile_key='missing',
                access_keys=('navigation.view',),
            ),
        )
    )

    with pytest.raises(ValueError, match='Unknown profile'):
        configuration.validate_profiles(_profiles())


def test_configuration_resolves_access_from_profile_owned_by_users() -> None:
    effective = _configuration().resolve('operator', profiles=_profiles())

    assert effective.profile_key == 'operator'
    assert effective.access_keys == ('navigation.view', 'kpis.manage')


def test_configuration_resolves_profile_without_grant_as_no_guaranteed_access() -> None:
    effective = AdaAccessConfiguration().resolve('viewer', profiles=_profiles())

    assert effective.profile_key == 'viewer'
    assert effective.access_keys == ()


def test_configuration_rejects_unknown_runtime_profile() -> None:
    with pytest.raises(ValueError, match='Unknown profile'):
        _configuration().resolve('missing', profiles=_profiles())


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
        profile_access=(
            ProfileAccessGrant(
                profile_key='administrator',
                access_keys=('kpis.manage',),
            ),
        ),
    )

    configuration.validate_profiles(profiles)
    effective = configuration.resolve('administrator', profiles=profiles)

    assert effective.profile_key == 'administrator'
    assert effective.access_keys == ('kpis.manage',)


def test_configuration_rejects_legacy_user_profile_assignment_document() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='contract is invalid'):
        AdaAccessConfiguration.from_document(
            {
                'user_profiles': [
                    {
                        'user_id': 'user-1',
                        'profile_keys': ['operator'],
                    }
                ],
                'profile_access': [],
            }
        )
