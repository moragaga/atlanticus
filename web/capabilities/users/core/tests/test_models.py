import pytest

from atlanticus.web.users.authority import (
    BASIC_AUTHORITY_KEY,
    GUEST_AUTHORITY_KEY,
    LOCAL_AUTHORITY_KEY,
    ROOT_AUTHORITY_KEY,
)
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    EffectiveUser,
    PendingUserRecord,
    ResolvedUserRecord,
    build_avatar_text,
)


def test_effective_user_contains_authority_and_optional_visuals() -> None:
    user = EffectiveUser(
        user_id='user-1',
        subject_id='oid-1',
        display_name='Jane Doe',
        email='JANE@EXAMPLE.COM',
        enabled=True,
        pending=False,
        avatar_text='JD',
        authority_key=BASIC_AUTHORITY_KEY,
    )

    assert user.email == 'jane@example.com'
    assert user.authority_key == BASIC_AUTHORITY_KEY
    assert user.avatar_background_color is None
    assert user.avatar_text_color is None
    assert user.has_full_access is False
    assert build_avatar_text('John Doe') == 'JD'

    root = EffectiveUser(
        user_id='user-2',
        subject_id='oid-2',
        display_name='Root User',
        email=None,
        enabled=True,
        pending=False,
        avatar_text='RU',
        authority_key=ROOT_AUTHORITY_KEY,
        avatar_background_color='#112233',
        avatar_text_color='#abcdef',
    )
    assert root.avatar_background_color == '#112233'
    assert root.avatar_text_color == '#ABCDEF'
    assert root.has_full_access is True


def test_pending_record_materializes_with_guest_authority() -> None:
    record = PendingUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-1'),
        issuer='entra',
        subject_id='subject-1',
        display_name='Pending User',
        email='PENDING@EXAMPLE.COM',
    )
    user = record.to_effective_user()

    assert user.user_id == record.user_id
    assert user.pending is True
    assert user.enabled is True
    assert user.authority_key == GUEST_AUTHORITY_KEY
    assert user.avatar_background_color == '#FF5722'
    assert user.avatar_text_color == '#FFFFFF'
    assert user.email == 'pending@example.com'


def test_pending_record_supports_missing_optional_metadata() -> None:
    record = PendingUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-1'),
        issuer='entra',
        subject_id='subject-1',
    )
    user = record.to_effective_user()

    assert user.display_name == 'Usuario pendiente'
    assert user.email is None
    assert user.authority_key == GUEST_AUTHORITY_KEY


def test_pending_record_rejects_identity_key_mismatch() -> None:
    with pytest.raises(UsersDefinitionError, match='must match authenticated identity'):
        PendingUserRecord(
            user_id=build_user_key(issuer='entra', subject_id='other-subject'),
            issuer='entra',
            subject_id='subject-1',
        )


def test_resolved_runtime_record_creates_non_pending_effective_user() -> None:
    user = ResolvedUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-1'),
        issuer='entra',
        subject_id='subject-1',
        display_name='Managed User',
        email='managed@example.com',
        enabled=True,
        authority_key=BASIC_AUTHORITY_KEY,
    ).to_effective_user()

    assert user.pending is False
    assert user.authority_key == BASIC_AUTHORITY_KEY


def test_resolved_runtime_record_accepts_functional_authority_without_profiles_core() -> None:
    user = ResolvedUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-1'),
        issuer='entra',
        subject_id='subject-1',
        display_name='Operator',
        email=None,
        enabled=True,
        authority_key='operator',
    ).to_effective_user()

    assert user.authority_key == 'operator'


def test_resolved_runtime_record_rejects_identity_key_mismatch() -> None:
    with pytest.raises(UsersDefinitionError, match='must match authenticated identity'):
        ResolvedUserRecord(
            user_id=build_user_key(issuer='entra', subject_id='other-subject'),
            issuer='entra',
            subject_id='subject-1',
            display_name='Managed User',
            email='managed@example.com',
            enabled=True,
            authority_key=BASIC_AUTHORITY_KEY,
        )


def test_pending_user_must_use_guest_authority() -> None:
    with pytest.raises(UsersDefinitionError, match='must use guest authority'):
        EffectiveUser(
            user_id='user-1',
            subject_id='subject-1',
            display_name='Pending User',
            email='pending@example.com',
            enabled=True,
            pending=True,
            avatar_text='PU',
            authority_key=BASIC_AUTHORITY_KEY,
        )


def test_pending_user_must_be_enabled() -> None:
    with pytest.raises(UsersDefinitionError, match='must be enabled'):
        EffectiveUser(
            user_id='user-1',
            subject_id='subject-1',
            display_name='Pending User',
            email='pending@example.com',
            enabled=False,
            pending=True,
            avatar_text='PU',
            authority_key=GUEST_AUTHORITY_KEY,
        )


def test_pending_user_rejects_avatar_color_override() -> None:
    with pytest.raises(UsersDefinitionError, match='avatar colors are fixed'):
        EffectiveUser(
            user_id='user-1',
            subject_id='subject-1',
            display_name='Pending User',
            email='pending@example.com',
            enabled=True,
            pending=True,
            avatar_text='PU',
            authority_key=GUEST_AUTHORITY_KEY,
            avatar_background_color='#000000',
        )


def test_resolved_user_cannot_use_guest_authority() -> None:
    with pytest.raises(UsersDefinitionError, match='cannot use guest authority'):
        ResolvedUserRecord(
            user_id=build_user_key(issuer='entra', subject_id='subject-1'),
            issuer='entra',
            subject_id='subject-1',
            display_name='Managed Guest',
            email='guest@example.com',
            enabled=True,
            authority_key=GUEST_AUTHORITY_KEY,
        )


def test_local_authority_is_reserved_for_local_runtime() -> None:
    with pytest.raises(UsersDefinitionError, match='cannot use local authority'):
        ResolvedUserRecord(
            user_id=build_user_key(issuer='entra', subject_id='subject-1'),
            issuer='entra',
            subject_id='subject-1',
            display_name='Managed Local',
            email=None,
            enabled=True,
            authority_key=LOCAL_AUTHORITY_KEY,
        )

    with pytest.raises(UsersDefinitionError, match='must use local authority'):
        ResolvedUserRecord(
            user_id=build_user_key(issuer='atlanticus-local', subject_id='local:john-doe'),
            issuer='atlanticus-local',
            subject_id='local:john-doe',
            display_name='John Doe',
            email=None,
            enabled=True,
            authority_key=BASIC_AUTHORITY_KEY,
            is_local=True,
        )
