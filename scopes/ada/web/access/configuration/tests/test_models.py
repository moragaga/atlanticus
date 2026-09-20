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
        access_keys=('navigation.view', 'kpis.manage'),
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


def test_configuration_round_trips_access_catalog_and_profile_assignments() -> None:
    configuration = _configuration()
    document = configuration.to_document()

    assert set(document) == {'access_keys', 'profile_access'}
    assert document['access_keys'] == ['kpis.manage', 'navigation.view']
    assert AdaAccessConfiguration.from_document(document) == configuration


def test_configuration_normalizes_and_sorts_access_definitions() -> None:
    configuration = AdaAccessConfiguration(access_keys=(' Navigation.View ', 'ALARMS.MANAGE'))

    assert configuration.access_keys == ('alarms.manage', 'navigation.view')


def test_configuration_rejects_duplicate_access_definitions() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='definitions must be unique'):
        AdaAccessConfiguration(access_keys=('navigation.view', 'NAVIGATION.VIEW'))


def test_configuration_rejects_profile_assignment_to_undefined_access() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='undefined access key'):
        AdaAccessConfiguration(
            access_keys=('navigation.view',),
            profile_access=(
                ProfileAccessGrant(
                    profile_key='operator',
                    access_keys=('kpis.manage',),
                ),
            ),
        )


def test_configuration_rejects_duplicate_profile_grants() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='profile grants must be unique'):
        AdaAccessConfiguration(
            access_keys=('navigation.view',),
            profile_access=(
                ProfileAccessGrant(profile_key='operator'),
                ProfileAccessGrant(profile_key='OPERATOR'),
            ),
        )


@pytest.mark.parametrize('profile_key', ['root', 'local'])
def test_configuration_rejects_explicit_grants_for_unrestricted_profiles(
    profile_key: str,
) -> None:
    with pytest.raises(AdaAccessDefinitionError, match='must not define explicit access grants'):
        AdaAccessConfiguration(
            access_keys=('navigation.view',),
            profile_access=(
                ProfileAccessGrant(
                    profile_key=profile_key,
                    access_keys=('navigation.view',),
                ),
            ),
        )


def test_configuration_validates_profile_references() -> None:
    configuration = AdaAccessConfiguration(
        access_keys=('navigation.view',),
        profile_access=(
            ProfileAccessGrant(
                profile_key='missing',
                access_keys=('navigation.view',),
            ),
        ),
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


@pytest.mark.parametrize('profile_key', ['root', 'local'])
def test_configuration_resolves_unrestricted_profile_with_all_defined_access(
    profile_key: str,
) -> None:
    configuration = AdaAccessConfiguration(
        access_keys=('navigation.view', 'kpis.manage'),
    )

    effective = configuration.resolve(profile_key, profiles=_profiles())

    assert effective.profile_key == profile_key
    assert effective.access_keys == ('kpis.manage', 'navigation.view')


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
        access_keys=('kpis.manage',),
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


def test_configuration_requires_explicit_access_catalog() -> None:
    with pytest.raises(AdaAccessDefinitionError, match='contract is invalid'):
        AdaAccessConfiguration.from_document(
            {
                'profile_access': [
                    {
                        'profile_key': 'operator',
                        'access_keys': ['navigation.view'],
                    }
                ]
            }
        )
