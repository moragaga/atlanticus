import pytest

from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    EffectiveUser,
    PendingUserRecord,
    ResolvedUserRecord,
    build_avatar_text,
)


def _profile(key: str, label: str | None = None) -> ProfileDefinition:
    return ProfileDefinition(
        key=key,
        label=label or key.title(),
        background_color='#673AB7',
        text_color='#FFFFFF',
    )


def test_effective_user_contains_resolved_profile_and_visuals() -> None:
    profile = _profile('administrator', 'Administrador')
    user = EffectiveUser(
        user_id='user-1',
        subject_id='oid-1',
        display_name='Jane Doe',
        email='JANE@EXAMPLE.COM',
        enabled=True,
        pending=False,
        avatar_text='JD',
        profile=profile,
    )
    assert user.email == 'jane@example.com'
    assert user.profile is profile
    assert user.avatar_background_color == profile.background_color
    assert user.avatar_text_color == profile.text_color
    assert build_avatar_text('John Doe') == 'JD'

    local_profile = _profile('local', 'Local')
    local_user = EffectiveUser(
        user_id='local-user',
        subject_id='local:john-doe',
        display_name='John Doe',
        email='john.doe@local.atlanticus',
        enabled=True,
        pending=False,
        avatar_text='JD',
        profile=local_profile,
        avatar_background_color='#112233',
        avatar_text_color='#ABCDEF',
        is_local=True,
    )
    assert local_user.avatar_background_color == '#112233'
    assert local_user.avatar_text_color == '#ABCDEF'


def test_pending_record_materializes_without_profile_or_managed_state() -> None:
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
    assert user.profile is None
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
    assert user.profile is None


def test_pending_record_rejects_identity_key_mismatch() -> None:
    with pytest.raises(UsersDefinitionError, match='must match authenticated identity'):
        PendingUserRecord(
            user_id=build_user_key(issuer='entra', subject_id='other-subject'),
            issuer='entra',
            subject_id='subject-1',
        )


def test_resolved_runtime_record_creates_non_pending_effective_user() -> None:
    profile = _profile('administrator', 'Administrador')
    user = ResolvedUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-1'),
        issuer='entra',
        subject_id='subject-1',
        display_name='Managed User',
        email='managed@example.com',
        enabled=True,
        profile_key='administrator',
    ).to_effective_user(profile=profile)
    assert user.pending is False
    assert user.profile is profile


def test_resolved_runtime_record_rejects_identity_key_mismatch() -> None:
    with pytest.raises(UsersDefinitionError, match='must match authenticated identity'):
        ResolvedUserRecord(
            user_id=build_user_key(issuer='entra', subject_id='other-subject'),
            issuer='entra',
            subject_id='subject-1',
            display_name='Managed User',
            email='managed@example.com',
            enabled=True,
            profile_key='administrator',
        )


def test_pending_user_must_not_have_profile() -> None:
    with pytest.raises(UsersDefinitionError, match='must not have a profile'):
        EffectiveUser(
            user_id='user-1',
            subject_id='subject-1',
            display_name='Pending User',
            email='pending@example.com',
            enabled=True,
            pending=True,
            avatar_text='PU',
            profile=_profile('administrator'),
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
            profile=None,
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
            profile=None,
            avatar_background_color='#000000',
        )


def test_resolved_user_requires_profile() -> None:
    with pytest.raises(UsersDefinitionError, match='must have a profile'):
        EffectiveUser(
            user_id='user-1',
            subject_id='subject-1',
            display_name='Managed User',
            email='managed@example.com',
            enabled=True,
            pending=False,
            avatar_text='MU',
            profile=None,
        )


def test_guest_profile_key_is_not_valid_for_resolved_user() -> None:
    with pytest.raises(UsersDefinitionError, match='cannot use guest profile key'):
        EffectiveUser(
            user_id='user-1',
            subject_id='subject-1',
            display_name='Managed Guest',
            email='guest@example.com',
            enabled=True,
            pending=False,
            avatar_text='MG',
            profile=_profile('guest', 'Guest'),
        )


def test_resolved_runtime_record_cannot_use_guest_profile_key() -> None:
    with pytest.raises(UsersDefinitionError, match='cannot use guest profile key'):
        ResolvedUserRecord(
            user_id=build_user_key(issuer='entra', subject_id='subject-1'),
            issuer='entra',
            subject_id='subject-1',
            display_name='Managed Guest',
            email='guest@example.com',
            enabled=True,
            profile_key='guest',
        )


def test_profiles_core_can_still_use_guest_key_outside_users_semantics() -> None:
    catalog = ProfileCatalog(profiles=(_profile('guest', 'Guest-like functional profile'),))

    assert catalog.require('guest').label == 'Guest-like functional profile'
