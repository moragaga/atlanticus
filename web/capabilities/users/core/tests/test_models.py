import pytest

from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.models import EffectiveUser, ResolvedUserRecord, build_avatar_text
from atlanticus.web.users.profiles import ProfileCatalog


def test_effective_user_contains_resolved_profile_and_visuals() -> None:
    profile = ProfileCatalog().require('administrator')
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
    assert user.profile.label == 'Administrador'
    assert user.avatar_background_color == profile.background_color
    assert user.avatar_text_color == profile.text_color
    assert build_avatar_text('John Doe') == 'JD'

    local_user = EffectiveUser(
        user_id='local-user',
        subject_id='local:john-doe',
        display_name='John Doe',
        email='john.doe@local.atlanticus',
        enabled=True,
        pending=False,
        avatar_text='JD',
        profile=ProfileCatalog().require('local'),
        avatar_background_color='#112233',
        avatar_text_color='#ABCDEF',
        is_local=True,
    )

    assert local_user.avatar_background_color == '#112233'
    assert local_user.avatar_text_color == '#ABCDEF'


def test_resolved_source_record_creates_non_pending_effective_user() -> None:
    profile = ProfileCatalog().require('administrator')
    user = ResolvedUserRecord(
        user_id='user-1',
        subject_id='subject-1',
        display_name='Managed User',
        email='managed@example.com',
        enabled=True,
        profile_key='administrator',
    ).to_effective_user(profile=profile)

    assert user.pending is False
    assert user.profile.key == 'administrator'


def test_pending_user_requires_guest_profile() -> None:
    with pytest.raises(UsersDefinitionError, match='must use guest profile'):
        EffectiveUser(
            user_id='pending:1',
            subject_id='subject-1',
            display_name='Pending User',
            email='pending@example.com',
            enabled=True,
            pending=True,
            avatar_text='PU',
            profile=ProfileCatalog().require('administrator'),
        )


def test_pending_user_must_be_enabled() -> None:
    with pytest.raises(UsersDefinitionError, match='must be enabled'):
        EffectiveUser(
            user_id='pending:1',
            subject_id='subject-1',
            display_name='Pending User',
            email='pending@example.com',
            enabled=False,
            pending=True,
            avatar_text='PU',
            profile=ProfileCatalog().require('guest'),
        )


def test_guest_profile_is_reserved_for_pending_users() -> None:
    with pytest.raises(UsersDefinitionError, match='reserved for pending users'):
        EffectiveUser(
            user_id='user-1',
            subject_id='subject-1',
            display_name='Managed Guest',
            email='guest@example.com',
            enabled=True,
            pending=False,
            avatar_text='MG',
            profile=ProfileCatalog().require('guest'),
        )


def test_resolved_source_record_cannot_use_guest_profile() -> None:
    with pytest.raises(UsersDefinitionError, match='cannot use guest profile'):
        ResolvedUserRecord(
            user_id='user-1',
            subject_id='subject-1',
            display_name='Managed Guest',
            email='guest@example.com',
            enabled=True,
            profile_key='guest',
        )
