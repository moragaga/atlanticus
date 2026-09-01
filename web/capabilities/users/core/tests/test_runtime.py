from flask import Flask

from atlanticus.web.identity.access import AccessDecision, AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.profiles import ProfileCatalog
from atlanticus.web.users.runtime import UsersRuntime


def _access(load_id: str) -> AccessSnapshot:
    return AccessSnapshot.resolved(
        load_id=load_id,
        identity=AuthenticatedIdentity(
            provider_key='local',
            issuer='atlanticus-local',
            subject_id='local:john-doe',
        ),
        decision=AccessDecision(status=AccessStatus.READY, user_id='user-1'),
    )


def _user() -> EffectiveUser:
    return EffectiveUser(
        user_id='user-1',
        subject_id='local:john-doe',
        display_name='John Doe',
        email='john.doe@local.atlanticus',
        enabled=True,
        pending=False,
        avatar_text='JD',
        profile=ProfileCatalog().require('local'),
    )


def test_users_snapshot_is_valid_only_for_matching_page_load() -> None:
    server = Flask(__name__)
    server.secret_key = 'test-only'
    runtime = UsersRuntime()

    with server.test_request_context('/'):
        runtime.store(load_id='load-1', user=_user())
        assert runtime.current(_access('load-1')).display_name == 'John Doe'
        assert runtime.current_or_none(_access('load-2')) is None
