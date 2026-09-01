import pytest

from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
    NavigationProjectionIssue,
    compose_navigation_configuration_services,
)
from atlanticus.web.navigation.configuration.adapters import (
    MemoryNavigationConfigurationStore,
    MemoryNavigationProjectionRepository,
)
from atlanticus.web.navigation.configuration.errors import (
    NavigationConfigurationProjectionError,
    NavigationConfigurationSourceError,
)


def _catalog(label: str = 'Dashboard') -> NavigationConfigurationCatalog:
    return NavigationConfigurationCatalog(
        links=(
            NavigationLinkConfiguration(
                key='dashboard',
                label=label,
                href='/',
                allowed_profiles=('guest',),
            ),
            NavigationLinkConfiguration(
                key='logout',
                label='Logout',
                href='/.auth/logout',
                force_reload=True,
            ),
        ),
    )


def test_validate_publish_project_lifecycle_is_separated() -> None:
    source = MemoryNavigationConfigurationStore()
    projection = MemoryNavigationProjectionRepository()
    services = compose_navigation_configuration_services(
        source=source,
        publisher=source,
        projection=projection,
        audit_actor_provider=lambda: 'administrator',
    )
    catalog = _catalog()

    validation = services.administration.validate_catalog(catalog)
    assert validation.valid is True
    assert source.fetch_bundle() is None

    publication = services.administration.publish_catalog(
        catalog,
        expected_source_revision=None,
    )
    assert publication.published is True
    assert len(source.list_history()) == 1
    assert projection.load() is None

    result = services.projection_workflow.project(publication.source_revision)
    assert result.projected is True
    assert projection.load().source_revision == publication.source_revision
    assert projection.load().definition.home_route_key is None
    assert projection.load().definition.find_link('logout').force_reload is True


def test_republishing_same_content_does_not_create_history_copy() -> None:
    source = MemoryNavigationConfigurationStore()
    services = compose_navigation_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryNavigationProjectionRepository(),
        audit_actor_provider=lambda: 'administrator',
    )
    catalog = _catalog()

    first = services.administration.publish_catalog(catalog, expected_source_revision=None)
    second = services.administration.publish_catalog(
        catalog,
        expected_source_revision=first.source_revision,
    )

    assert second.published is False
    assert len(source.list_history()) == 1


def test_stale_source_revision_is_rejected() -> None:
    source = MemoryNavigationConfigurationStore()
    services = compose_navigation_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryNavigationProjectionRepository(),
        audit_actor_provider=lambda: 'administrator',
    )
    first = services.administration.publish_catalog(_catalog(), expected_source_revision=None)

    with pytest.raises(NavigationConfigurationSourceError):
        services.administration.publish_catalog(
            _catalog('Operations'),
            expected_source_revision='stale',
        )

    assert source.fetch_bundle().revision == first.source_revision


def test_optional_validator_can_reject_catalog_without_creating_users_dependency() -> None:
    def validator(catalog: NavigationConfigurationCatalog):
        if 'guest' in catalog.configured_profiles():
            return (
                NavigationProjectionIssue(
                    code='profile.invalid',
                    message='Profile is not available',
                    path='links[0].allowed_profiles',
                ),
            )
        return ()

    source = MemoryNavigationConfigurationStore()
    services = compose_navigation_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryNavigationProjectionRepository(),
        audit_actor_provider=lambda: 'administrator',
        validators=(validator,),
    )

    validation = services.administration.validate_catalog(_catalog())
    assert validation.valid is False

    with pytest.raises(NavigationConfigurationSourceError):
        services.administration.publish_catalog(_catalog(), expected_source_revision=None)


def test_projection_revalidates_published_source() -> None:
    source = MemoryNavigationConfigurationStore()
    base = compose_navigation_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryNavigationProjectionRepository(),
        audit_actor_provider=lambda: 'administrator',
    )
    published = base.administration.publish_catalog(_catalog(), expected_source_revision=None)

    rejecting = compose_navigation_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryNavigationProjectionRepository(),
        audit_actor_provider=lambda: 'administrator',
        validators=(
            lambda _catalog: (
                NavigationProjectionIssue(code='blocked', message='Blocked by composition'),
            ),
        ),
    )

    with pytest.raises(NavigationConfigurationProjectionError):
        rejecting.projection_workflow.project(published.source_revision)
