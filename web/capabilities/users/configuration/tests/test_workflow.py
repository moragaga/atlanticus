import pytest

from atlanticus.web.users.configuration import (
    UserConfiguration,
    UserProfileConfiguration,
    UsersConfigurationCatalog,
    compose_users_configuration_services,
)
from atlanticus.web.users.configuration.adapters import (
    MemoryPendingUsersReader,
    MemoryUsersConfigurationStore,
    MemoryUsersProjectionRepository,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationSourceError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import PendingUserRecord


def _catalog(label: str = 'Operador') -> UsersConfigurationCatalog:
    return UsersConfigurationCatalog(
        administrator_background_color='#673AB7',
        guest_background_color='#FF5722',
        profiles=(
            UserProfileConfiguration(
                key='operator',
                label=label,
                background_color='#123456',
            ),
        ),
        users=(
            UserConfiguration.create(
                display_name='User One',
                email='one@example.com',
                profile_key='operator',
                issuer='entra',
                subject_id='configured-subject',
            ),
        ),
    )


def test_validate_publish_project_lifecycle_is_separated() -> None:
    source = MemoryUsersConfigurationStore()
    projection = MemoryUsersProjectionRepository()
    services = compose_users_configuration_services(
        source=source,
        publisher=source,
        projection=projection,
        pending=MemoryPendingUsersReader(),
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
    assert projection.load_state() is None

    result = services.projection_workflow.project(publication.source_revision)
    assert result.projected is True
    assert projection.load_state().source_revision == publication.source_revision


def test_republishing_same_content_does_not_create_history_copy() -> None:
    source = MemoryUsersConfigurationStore()
    services = compose_users_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryUsersProjectionRepository(),
        pending=MemoryPendingUsersReader(),
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
    source = MemoryUsersConfigurationStore()
    services = compose_users_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryUsersProjectionRepository(),
        pending=MemoryPendingUsersReader(),
        audit_actor_provider=lambda: 'administrator',
    )
    first = services.administration.publish_catalog(_catalog(), expected_source_revision=None)

    with pytest.raises(UsersConfigurationSourceError):
        services.administration.publish_catalog(
            _catalog('Nuevo nombre'),
            expected_source_revision='stale',
        )

    assert source.fetch_bundle().revision == first.source_revision


def test_pending_identity_remains_visible_until_it_is_materialized_in_source() -> None:
    source = MemoryUsersConfigurationStore()
    pending = MemoryPendingUsersReader(
        users=[
            PendingUserRecord(
                user_id=build_user_key(issuer='entra', subject_id='subject-1'),
                issuer='entra',
                subject_id='subject-1',
                display_name='User One',
                email='one@example.com',
            )
        ]
    )
    services = compose_users_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryUsersProjectionRepository(),
        pending=pending,
        audit_actor_provider=lambda: 'administrator',
    )
    manual = _catalog()
    first = services.administration.publish_catalog(manual, expected_source_revision=None)

    assert tuple(user.user_id for user in services.administration.list_pending()) == (
        build_user_key(issuer='entra', subject_id='subject-1'),
    )

    materialized_user = UserConfiguration.create(
        issuer='entra',
        subject_id='subject-1',
        display_name='User One',
        email='one@example.com',
        profile_key='operator',
    )
    materialized = UsersConfigurationCatalog(
        administrator_background_color=manual.administrator_background_color,
        administrator_text_color=manual.administrator_text_color,
        guest_background_color=manual.guest_background_color,
        guest_text_color=manual.guest_text_color,
        profiles=manual.profiles,
        users=(materialized_user,),
    )
    services.administration.publish_catalog(
        materialized,
        expected_source_revision=first.source_revision,
    )

    assert services.administration.list_pending() == ()


def test_pending_identity_can_be_listed_without_optional_metadata() -> None:
    pending_user = PendingUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-1'),
        issuer='entra',
        subject_id='subject-1',
    )
    source = MemoryUsersConfigurationStore()
    services = compose_users_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryUsersProjectionRepository(),
        pending=MemoryPendingUsersReader(users=[pending_user]),
        audit_actor_provider=lambda: 'administrator',
    )

    assert services.administration.list_pending() == (pending_user,)


def test_pending_identity_matching_preserves_exact_issuer() -> None:
    source = MemoryUsersConfigurationStore()
    pending_user = PendingUserRecord(
        user_id=build_user_key(issuer='ENTRA', subject_id='configured-subject'),
        issuer='ENTRA',
        subject_id='configured-subject',
        display_name='User One',
        email='one@example.com',
    )
    services = compose_users_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryUsersProjectionRepository(),
        pending=MemoryPendingUsersReader(users=[pending_user]),
        audit_actor_provider=lambda: 'administrator',
    )

    services.administration.publish_catalog(_catalog(), expected_source_revision=None)

    assert services.administration.list_pending() == (pending_user,)
