from atlanticus.web.users.models import EffectiveUser, ResolvedUserRecord, build_avatar_text
from atlanticus.web.users.profiles import ProfileCatalog


def test_effective_user_contains_resolved_profile_and_full_access_policy() -> None:
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
    assert user.has_full_access is True
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
    )
    assert local_user.has_full_access is True
    assert local_user.avatar_background_color == '#112233'
    assert local_user.avatar_text_color == '#ABCDEF'


def test_resolved_record_preserves_pending_state() -> None:
    profile = ProfileCatalog().require('guest')
    user = ResolvedUserRecord(
        user_id='pending:1',
        subject_id='subject-1',
        display_name='Pending User',
        email='pending@example.com',
        enabled=True,
        profile_key='guest',
        pending=True,
    ).to_effective_user(profile=profile)

    assert user.pending is True
