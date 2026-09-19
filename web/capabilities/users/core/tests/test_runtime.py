from flask import Flask

from atlanticus.web.identity.access import AccessDecision, AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.runtime import UsersRuntime, UsersSnapshot


def _access(load_id: str) -> AccessSnapshot:
    identity = AuthenticatedIdentity(provider_key='entra', issuer='entra', subject_id='oid-1')
    return AccessSnapshot.resolved(
        load_id=load_id,
        identity=identity,
        decision=AccessDecision(status=AccessStatus.READY, user_id='user-1'),
    )


def _managed_user() -> EffectiveUser:
    return EffectiveUser(
        user_id='user-1',
        subject_id='oid-1',
        display_name='John Doe',
        email='john.doe@example.com',
        enabled=True,
        avatar_text='JD',
        profile_key='basic',
        avatar_background_color='#112233',
        avatar_text_color='#FFFFFF',
    )


def test_runtime_snapshot_is_scoped_to_page_load() -> None:
    server = Flask(__name__)
    server.secret_key = 'test-only'
    runtime = UsersRuntime()

    with server.test_request_context('/'):
        runtime.store(load_id='load-1', user=_managed_user())

        assert runtime.current(_access('load-1')) == _managed_user()
        assert runtime.current_or_none(_access('load-2')) is None


def test_promoted_snapshot_roundtrips_profile_and_visuals() -> None:
    managed = _managed_user()
    snapshot = UsersSnapshot(load_id='load-managed', user=managed)

    restored = UsersSnapshot.from_session(snapshot.to_session())

    assert restored.user.profile_key == 'basic'
    assert restored.user.avatar_background_color == '#112233'
    assert restored.user.avatar_text_color == '#FFFFFF'
    assert restored.user.is_local is False
    assert 'authority_key' not in snapshot.to_session()['user']
