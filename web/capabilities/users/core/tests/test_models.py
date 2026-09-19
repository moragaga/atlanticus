from dataclasses import replace

import pytest

from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    DiscoveredUser,
    EffectiveUser,
    UserRecord,
    UsersRegistrySnapshot,
    build_avatar_text,
)


def _user(*, subject_id: str = 'subject-1', profile_key: str = 'basic') -> UserRecord:
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id=subject_id),
        issuer='entra',
        subject_id=subject_id,
        display_name='Managed User',
        email='MANAGED@EXAMPLE.COM',
        enabled=True,
        profile_key=profile_key,
    )


def test_user_record_persists_profile_key_without_embedding_profile_metadata() -> None:
    user = _user(profile_key='guest')

    assert user.email == 'managed@example.com'
    assert user.profile_key == 'guest'
    assert user.to_effective_user().profile_key == 'guest'
    assert 'profile_key' in user.to_document()
    assert 'authority_key' not in user.to_document()


def test_user_record_accepts_configured_profile_key_and_rejects_local() -> None:
    configured = replace(
        _user(),
        profile_key='11111111-1111-4111-8111-111111111111',
    )

    assert configured.profile_key == '11111111-1111-4111-8111-111111111111'
    with pytest.raises(UsersDefinitionError, match='must not be local'):
        replace(configured, profile_key='local')


def test_root_user_materializes_full_access() -> None:
    user = _user(profile_key='root').to_effective_user()

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


def test_discovered_user_promotes_to_explicit_profile_key() -> None:
    discovered = DiscoveredUser(
        issuer='entra',
        subject_id='subject-1',
        display_name='Jane Doe',
        email='JANE@EXAMPLE.COM',
    )

    promoted = discovered.promote_as(profile_key='guest')

    assert promoted.user_id == discovered.user_id
    assert promoted.display_name == 'Jane Doe'
    assert promoted.email == 'jane@example.com'
    assert promoted.profile_key == 'guest'


def test_registry_rejects_duplicate_identity() -> None:
    first = _user()
    duplicate = replace(first, display_name='Other Name')

    with pytest.raises(UsersDefinitionError, match='ids must be unique'):
        UsersRegistrySnapshot(users=(first, duplicate))


def test_effective_nonlocal_user_rejects_local_profile() -> None:
    with pytest.raises(UsersDefinitionError, match='must not be local'):
        EffectiveUser(
            user_id='user-1',
            subject_id='subject-1',
            display_name='Local',
            email=None,
            enabled=True,
            avatar_text='LO',
            profile_key='local',
        )
