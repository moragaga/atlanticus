import pytest

from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
    NavigationProfileOption,
    create_navigation_profile_options_validator,
)


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
                allowed_profiles=(profile_key,),
            ),
        )
    )


@pytest.mark.parametrize('profile_key', ('basic', 'root', 'guest', 'local'))
def test_profile_options_validator_accepts_declared_profile(profile_key: str) -> None:
    validator = create_navigation_profile_options_validator(_profile_options)

    assert validator(_catalog(profile_key)) == ()


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
