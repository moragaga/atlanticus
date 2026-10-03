from flask import Flask

from ada.web.application.configuration_manager.composition import build_configuration_manager_surface
from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic.manager_principal import compose_integrated_manager_dependencies
from atlanticus.web.identity.access import AccessDecision, AccessRuntime, AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.manager import ManagerSurface
from atlanticus.web.users.local import LOCAL_ISSUER
from atlanticus.web.users.runtime import UsersRuntime


def _access(subject, *, issuer=LOCAL_ISSUER, provider='local'):
    return AccessSnapshot.resolved(
        load_id='load-1',
        identity=AuthenticatedIdentity(
            provider_key=provider,
            issuer=issuer,
            subject_id=subject,
        ),
        decision=AccessDecision(status=AccessStatus.READY),
    )


def test_known_local_user_receives_local_manager_override(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    app.secret_key = 'test'
    access = AccessRuntime()
    dependencies = compose_integrated_manager_dependencies(
        stores=create_local_configuration_manager_stores(source_root=tmp_path / 'source'),
        access_runtime=access,
        users_runtime=UsersRuntime(),
    )
    with app.test_request_context('/manager'):
        access.store(_access('local:jane-doe'))
        principal = dependencies.principal_provider()
        surface = ManagerSurface(build_configuration_manager_surface(dependencies))
        visible = surface.registry.visible_items(principal, surface.authorization)
    assert principal.is_local
    assert principal.profile_keys == ('local',)
    assert principal.administrative_override
    assert 'users' in {item.key for item in visible}


def test_untrusted_identity_does_not_inherit_local_override(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    app = Flask(__name__)
    app.secret_key = 'test'
    access = AccessRuntime()
    dependencies = compose_integrated_manager_dependencies(
        stores=create_local_configuration_manager_stores(source_root=tmp_path / 'source'),
        access_runtime=access,
        users_runtime=UsersRuntime(),
    )
    with app.test_request_context('/manager'):
        access.store(_access('local:jane-doe', issuer='entra', provider='entra'))
        principal = dependencies.principal_provider()
    assert not principal.is_local
    assert not principal.administrative_override
