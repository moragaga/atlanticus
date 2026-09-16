from flask import Flask

from atlanticus.web.identity.access import AccessDecision, AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.authority import BASIC_AUTHORITY_KEY
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import EffectiveUser, PendingUserRecord
from atlanticus.web.users.runtime import UsersRuntime, UsersSnapshot


def _access(load_id: str, *, user_id: str = 'user-1') -> AccessSnapshot:
    return AccessSnapshot.resolved(
        load_id=load_id,
        identity=AuthenticatedIdentity(
            provider_key='local',
            issuer='atlanticus-local',
            subject_id='local:john-doe',
        ),
        decision=AccessDecision(status=AccessStatus.READY, user_id=user_id),
    )


def _managed_user() -> EffectiveUser:
    return EffectiveUser(
        user_id='user-1',
        subject_id='local:john-doe',
        display_name='John Doe',
        email='john.doe@local.atlanticus',
        enabled=True,
        pending=False,
        avatar_text='JD',
        authority_key=BASIC_AUTHORITY_KEY,
        avatar_background_color='#112233',
        avatar_text_color='#FFFFFF',
    )


def _pending_user() -> EffectiveUser:
    return PendingUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-1'),
        issuer='entra',
        subject_id='subject-1',
        display_name='Pending User',
    ).to_effective_user()


def test_users_snapshot_is_valid_only_for_matching_page_load() -> None:
    server = Flask(__name__)
    server.secret_key = 'test-only'
    runtime = UsersRuntime()

    with server.test_request_context('/'):
        runtime.store(load_id='load-1', user=_managed_user())
        assert runtime.current(_access('load-1')).display_name == 'John Doe'
        assert runtime.current_or_none(_access('load-2')) is None


def test_pending_snapshot_roundtrips_guest_authority() -> None:
    pending = _pending_user()
    snapshot = UsersSnapshot(load_id='load-pending', user=pending)

    restored = UsersSnapshot.from_session(snapshot.to_session())

    assert restored.user.pending is True
    assert restored.user.authority_key == 'guest'
    assert restored.user.avatar_background_color == '#FF5722'
    assert restored.user.avatar_text_color == '#FFFFFF'


def test_managed_snapshot_roundtrips_authority_and_visuals() -> None:
    managed = _managed_user()
    snapshot = UsersSnapshot(load_id='load-managed', user=managed)

    restored = UsersSnapshot.from_session(snapshot.to_session())

    assert restored.user.pending is False
    assert restored.user.authority_key == BASIC_AUTHORITY_KEY
    assert restored.user.avatar_background_color == '#112233'
    assert restored.user.avatar_text_color == '#FFFFFF'
