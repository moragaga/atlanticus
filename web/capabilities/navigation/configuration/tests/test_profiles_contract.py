import pytest

from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
    create_navigation_profile_catalog_validator,
)
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition


def _profile_catalog() -> ProfileCatalog:
    return ProfileCatalog(
        profiles=(
            ProfileDefinition(
                key='guest',
                label='Guest',
                background_color='#111111',
            ),
        )
    )


def _catalog(profile_key: str) -> NavigationConfigurationCatalog:
    return NavigationConfigurationCatalog(
        links=(
            NavigationLinkConfiguration(
                key='home',
                label='Home',
                href='/',
                allowed_profiles=(profile_key,),
            ),
        )
    )


def test_profile_catalog_validator_accepts_known_profile() -> None:
    validator = create_navigation_profile_catalog_validator(_profile_catalog)

    assert validator(_catalog('guest')) == ()


def test_profile_catalog_validator_reports_unknown_profile() -> None:
    validator = create_navigation_profile_catalog_validator(_profile_catalog)

    issues = validator(_catalog('operator'))

    assert len(issues) == 1
    assert issues[0].code == 'navigation.profile.unknown'
    assert issues[0].message == "Unknown navigation profile 'operator'"


def test_profile_catalog_validator_does_not_hide_provider_failures() -> None:
    def provider() -> ProfileCatalog:
        raise RuntimeError('profile catalog unavailable')

    validator = create_navigation_profile_catalog_validator(provider)

    with pytest.raises(RuntimeError, match='profile catalog unavailable'):
        validator(_catalog('guest'))
