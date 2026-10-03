import pytest

from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
    NavigationProfileOption,
    create_navigation_profile_options_validator,
)
from atlanticus.web.navigation.configuration.errors import NavigationConfigurationValidationError


def _profile_options() -> tuple[NavigationProfileOption, ...]:
    return tuple(
        NavigationProfileOption(key=key, label=key.title())
        for key in ('basic', 'root', 'guest', 'local')
    )


def _catalog(profile_key: str) -> NavigationConfigurationCatalog:
    return NavigationConfigurationCatalog(
        links=(
            NavigationLinkConfiguration(
                key='home',
                label='Home',
                href='/',
                access_mode='restricted',
                allowed_profiles=(profile_key,),
            ),
        )
    )


@pytest.mark.parametrize('profile_key', ('basic', 'guest'))
def test_profile_options_validator_accepts_declared_ordinary_profile(profile_key: str) -> None:
    validator = create_navigation_profile_options_validator(_profile_options)

    assert validator(_catalog(profile_key)) == ()


@pytest.mark.parametrize('profile_key', ('root', 'local'))
def test_root_and_local_are_not_explicit_navigation_grants(profile_key: str) -> None:
    with pytest.raises(NavigationConfigurationValidationError, match='cannot be explicit grants'):
        _catalog(profile_key)


def test_profile_options_validator_reports_unknown_profile() -> None:
    validator = create_navigation_profile_options_validator(_profile_options)

    issues = validator(_catalog('operator'))

    assert len(issues) == 1
    assert issues[0].code == 'navigation.profile.unknown'
    assert issues[0].message == "Unknown navigation profile 'operator'"


def test_profile_options_validator_does_not_hide_provider_failures() -> None:
    def provider() -> tuple[NavigationProfileOption, ...]:
        raise RuntimeError('profile options unavailable')

    validator = create_navigation_profile_options_validator(provider)

    with pytest.raises(RuntimeError, match='profile options unavailable'):
        validator(_catalog('guest'))
