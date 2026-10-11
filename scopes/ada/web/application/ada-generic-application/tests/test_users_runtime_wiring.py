from __future__ import annotations

import pytest

from ada.web.application.configuration_manager.local_runtime import (
    InProcessUsersRuntimeStore,
    create_local_configuration_manager_stores,
)
from ada.web.application.configuration_manager.users_publication import (
    AdaUsersAdministrationService,
)
from ada.web.application.generic import manager_principal
from atlanticus.web.compositions.users_manager import USERS_ADMINISTRATION_SERVICE
from atlanticus.web.identity.access import AccessRuntime
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.runtime import UsersRuntime


def _user(subject):
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id=subject),
        issuer='issuer',
        subject_id=subject,
        display_name=subject,
    )
    return RuntimeUser(
        identity=identity,
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
    )


def test_local_upsert_preserves_other_users_and_rejects_invalid_payload():
    alice, bob = _user('alice'), _user('bob')
    store = InProcessUsersRuntimeStore((alice, bob))
    changed = RuntimeUser(
        identity=alice.identity,
        enabled=False,
        profile=RuntimeProfile.from_profile(ROOT_PROFILE),
    )
    assert store.upsert_user(changed) == changed
    assert store.list_users() == tuple(sorted((changed, bob), key=lambda u: u.user_id))
    assert store.upsert_user(changed) == changed
    with pytest.raises(TypeError, match='RuntimeUser'):
        store.upsert_user('invalid')


def test_integrated_manager_wires_individual_publication(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path)
    captured = []

    class Materializer:
        def __init__(self, *, stores):
            self.stores = stores

        def publish_user(self, user_id, *, writer):
            captured.append(user_id)
            user = next(
                user for user in self.stores.users_registry.load().users if user.user_id == user_id
            )
            membership = self.stores.users_memberships.load().get(user_id)
            return writer.upsert_user(
                RuntimeUser(
                    identity=user,
                    enabled=membership.enabled,
                    profile=RuntimeProfile.from_profile(BASIC_PROFILE),
                )
            )

    monkeypatch.setattr(manager_principal, 'AdaUsersRuntimeMaterializer', Materializer)
    deps = manager_principal.compose_integrated_manager_dependencies(
        stores=stores,
        access_runtime=AccessRuntime(),
        users_runtime=UsersRuntime(),
    )
    services = ServiceRegistry()
    deps.users_entry.web_module.register_services(services)
    administration = services.require(USERS_ADMINISTRATION_SERVICE, AdaUsersAdministrationService)
    alice = _user('alice').identity
    stores.users_registry.replace((alice,), expected_version=None)
    administration.promote(
        alice.user_id,
        profile_key='basic',
        expected_registry_version=stores.users_registry.load().version,
        expected_membership_version=stores.users_memberships.load().version,
    )
    assert captured == [alice.user_id]
    assert stores.users_runtime.resolve(
        AuthenticatedIdentity(
            provider_key='entra', issuer=alice.issuer, subject_id=alice.subject_id
        )
    ).user_id == alice.user_id
