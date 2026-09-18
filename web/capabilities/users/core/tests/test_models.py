from dataclasses import replace

import pytest

from atlanticus.web.users.authority import BASIC_AUTHORITY_KEY, ROOT_AUTHORITY_KEY
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    DiscoveredUser,
    EffectiveUser,
    UserRecord,
    UsersRegistrySnapshot,
    build_avatar_text,
)


def _user(*, subject_id: str = 'subject-1', authority_key: str = BASIC_AUTHORITY_KEY) -> UserRecord:
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id=subject_id),
        issuer='entra',
        subject_id=subject_id,
        display_name='Managed User',
        email='MANAGED@EXAMPLE.COM',
        enabled=True,
        authority_key=authority_key,
    )


def test_user_record_is_global_and_does_not_accept_application_profile_authority() -> None:
    user = _user()

    assert user.email == 'managed@example.com'
    assert user.authority_key == BASIC_AUTHORITY_KEY
    assert user.to_effective_user().has_full_access is False

    with pytest.raises(UsersDefinitionError, match='basic or root'):
        replace(user, authority_key='operator')


def test_root_user_materializes_full_access() -> None:
    user = _user(authority_key=ROOT_AUTHORITY_KEY).to_effective_user()

    assert user.has_full_access is True
    assert user.is_local is False
    assert build_avatar_text('John Doe') == 'JD'


def test_user_record_roundtrips_durable_document() -> None:
    original = replace(
        _user(),
        avatar_background_color='#112233',
        avatar_text_color='#abcdef',
    )

    restored = UserRecord.from_document(original.to_document())

    assert restored == original
    assert restored.avatar_text_color == '#ABCDEF'


def test_discovered_user_promotes_to_explicit_global_authority() -> None:
    discovered = DiscoveredUser(
        issuer='entra',
        subject_id='subject-1',
        display_name='Jane Doe',
        email='JANE@EXAMPLE.COM',
    )

    promoted = discovered.promote_as(authority_key=BASIC_AUTHORITY_KEY)

    assert promoted.user_id == discovered.user_id
    assert promoted.display_name == 'Jane Doe'
    assert promoted.email == 'jane@example.com'
    assert promoted.authority_key == BASIC_AUTHORITY_KEY


def test_registry_rejects_duplicate_identity() -> None:
    first = _user()
    duplicate = replace(first, display_name='Other Name')

    with pytest.raises(UsersDefinitionError, match='ids must be unique'):
        UsersRegistrySnapshot(users=(first, duplicate))


def test_effective_user_rejects_application_profile_authority() -> None:
    with pytest.raises(UsersDefinitionError, match='basic or root'):
        EffectiveUser(
            user_id='user-1',
            subject_id='subject-1',
            display_name='Operator',
            email=None,
            enabled=True,
            avatar_text='OP',
            authority_key='operator',
        )
