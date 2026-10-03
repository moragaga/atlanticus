from flask import Flask

from ada_command_center.web.application.generic.manager_principal import ManagerPrincipalBinding
from atlanticus.web.identity.access import (
    AccessDecision,
    AccessRuntime,
    AccessSnapshot,
    AccessStatus,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.local import LOCAL_ISSUER, LOCAL_USERS
from atlanticus.web.users.runtime import UsersRuntime


def test_trusted_local_identity_resolves_local_manager_principal() -> None:
    app = Flask(__name__)
    app.secret_key = 'test'
    local = LOCAL_USERS[0]
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    binding = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
        trusted_local_users=True,
    )
    access = AccessSnapshot.resolved(
        load_id='load-1',
        identity=AuthenticatedIdentity(
            provider_key='local',
            issuer=LOCAL_ISSUER,
            subject_id=local.subject_id,
        ),
        decision=AccessDecision(status=AccessStatus.READY),
    )

    with app.test_request_context('/manager'):
        access_runtime.store(access)
        principal = binding()

    assert principal.subject_id == local.subject_id
    assert principal.profile_keys == ('local',)
    assert principal.administrative_override is True
    assert principal.is_local is True
