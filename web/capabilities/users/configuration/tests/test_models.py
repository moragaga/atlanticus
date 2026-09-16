import pytest

from atlanticus.web.users.configuration import (
    UserConfiguration,
    UsersConfiguration,
    build_profile_key,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError
from atlanticus.web.users.identity import build_user_key


@pytest.mark.parametrize('profile_key', ['local', 'guest'])
def test_managed_user_rejects_non_assignable_profile_keys(profile_key: str) -> None:
    with pytest.raises(UsersConfigurationValidationError, match='cannot be assigned'):
        UserConfiguration.create(
            display_name='Managed User',
            email='managed@example.com',
            profile_key=profile_key,
            issuer='entra',
            subject_id='managed-user',
        )


@pytest.mark.parametrize(
    ('issuer', 'subject_id'),
    [(None, None), ('entra', None), (None, 'subject-1')],
)
def test_managed_user_requires_authenticated_identity(
    issuer: str | None,
    subject_id: str | None,
) -> None:
    with pytest.raises(UsersConfigurationValidationError, match='must not be empty'):
        UserConfiguration.create(
            display_name='Managed User',
            email='managed@example.com',
            profile_key='administrator',
            issuer=issuer,
            subject_id=subject_id,
        )


def test_managed_user_id_is_derived_from_authenticated_identity() -> None:
    user = UserConfiguration.create(
        display_name='Managed User',
        email='User@Example.com',
        profile_key='administrator',
        issuer='entra',
        subject_id='subject-1',
    )

    assert user.user_id == build_user_key(issuer='entra', subject_id='subject-1')
    assert user.email == 'user@example.com'


def test_managed_user_email_is_optional_and_roundtrips() -> None:
    user = UserConfiguration.create(
        display_name='Managed User',
        profile_key='administrator',
        issuer='entra',
        subject_id='subject-1',
    )

    assert user.email is None
    assert UserConfiguration.from_document(user.to_document()) == user


def test_users_configuration_allows_multiple_managed_users_without_email() -> None:
    users = tuple(
        UserConfiguration.create(
            display_name=f'User {index}',
            profile_key='administrator',
            issuer='entra',
            subject_id=f'subject-{index}',
        )
        for index in (1, 2)
    )

    configuration = UsersConfiguration(users=users)

    assert tuple(user.email for user in configuration.users) == (None, None)


def test_managed_user_rejects_invalid_non_empty_email() -> None:
    with pytest.raises(UsersConfigurationValidationError, match='email is invalid'):
        UserConfiguration.create(
            display_name='Managed User',
            email='not-an-email',
            profile_key='administrator',
            issuer='entra',
            subject_id='subject-1',
        )


def test_managed_user_rejects_user_id_from_another_identity() -> None:
    with pytest.raises(UsersConfigurationValidationError, match='match authenticated identity'):
        UserConfiguration.create(
            user_id=build_user_key(issuer='entra', subject_id='other-subject'),
            display_name='Managed User',
            email='managed@example.com',
            profile_key='administrator',
            issuer='entra',
            subject_id='subject-1',
        )


@pytest.mark.parametrize(
    'identity_fields',
    [{}, {'issuer': None, 'subject_id': None}],
)
def test_user_document_without_authenticated_identity_is_rejected(
    identity_fields: dict[str, object],
) -> None:
    with pytest.raises(UsersConfigurationValidationError, match='User contract is invalid'):
        UserConfiguration.from_document(
            {
                'user_id': 'user:incomplete',
                'display_name': 'Incomplete User',
                'email': 'user@example.com',
                'profile_key': 'administrator',
                'enabled': True,
                **identity_fields,
            }
        )


def test_profile_key_is_generated_from_display_label() -> None:
    assert build_profile_key('Operador Planta') == 'operador_planta'
    assert build_profile_key('Supervisión Mina') == 'supervision_mina'
