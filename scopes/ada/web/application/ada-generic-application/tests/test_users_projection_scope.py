from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.web.application.generic import manager_deployment
from ada.web.application.generic.manager_deployment import (
    open_durable_manager,
    resolve_durable_manager_configuration,
)
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.users.recovery import UsersRecoveryConflictError


def _settings(tool_namespace: str) -> AdaGenericSettings:
    return AdaGenericSettings.from_mapping({
        'ATLANTICUS_ENVIRONMENT': 'local',
        'ADA_APPLICATION_NAMESPACE': 'shared-users',
        'ADA_TOOL_NAMESPACE': tool_namespace,
        'ADA_TOOL_SOURCE_PROVIDER': 'blob',
        'ADA_TOOL_PROJECTION_PROVIDER': 'cosmos',
        'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME': 'configuration',
        'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING': 'UseDevelopmentStorage=true',
        'ADA_TOOL_PROJECTION_COSMOS_ENDPOINT': 'http://localhost:8081',
        'ADA_TOOL_PROJECTION_COSMOS_KEY': 'test-only',
        'ADA_TOOL_PROJECTION_COSMOS_DATABASE_NAME': 'shared-database',
    })


def test_two_tools_share_global_users_under_one_existing_application_namespace():
    first = resolve_durable_manager_configuration(_settings('mine'))
    second = resolve_durable_manager_configuration(_settings('flotation'))
    assert first.namespace.tool_prefix != second.namespace.tool_prefix
    assert first.namespace.application_prefix == second.namespace.application_prefix
    assert first.namespace.application_blob_name('users/users.json.gz') == (
        second.namespace.application_blob_name('users/users.json.gz')
    )
    assert first.resources.users_registry == second.resources.users_registry
    assert first.cosmos_settings == second.cosmos_settings


def test_users_projection_factory_defers_cosmos_lookup_and_uses_actual_issuer(monkeypatch):
    settings = _settings('mine')
    captured = []

    def fake_service(**kwargs):
        captured.append(kwargs)
        return object()

    monkeypatch.setattr(manager_deployment, 'UsersApprovedRecoveryService', fake_service)
    with open_durable_manager(settings) as runtime:
        assert callable(runtime.stores.users_recovery)
        assert captured == []
        monkeypatch.setattr(
            type(runtime.stores.users_promoted),
            'list_users',
            lambda _self: (SimpleNamespace(issuer='real-user-issuer'),),
        )
        runtime.stores.users_recovery()
        assert captured[-1]['identity_realm'] == 'real-user-issuer'
        assert captured[-1]['environment'] == 'local:shared-database'
        assert captured[-1]['application_key'] == 'shared-users'


def test_users_projection_cannot_invent_a_realm_for_empty_or_mixed_users(monkeypatch):
    with open_durable_manager(_settings('mine')) as runtime:
        users = []
        monkeypatch.setattr(
            type(runtime.stores.users_promoted),
            'list_users',
            lambda _self: tuple(users),
        )
        with pytest.raises(UsersRecoveryConflictError, match='identifiable issuer'):
            runtime.stores.users_recovery()
        users.extend((SimpleNamespace(issuer='a'), SimpleNamespace(issuer='b')))
        with pytest.raises(UsersRecoveryConflictError, match='identifiable issuer'):
            runtime.stores.users_recovery()


def test_independent_application_namespace_keeps_a_separate_user_registry():
    shared = _settings('mine')
    independent = shared.model_copy(update={'application_namespace': 'independent-users'})
    left = resolve_durable_manager_configuration(shared).namespace
    right = resolve_durable_manager_configuration(independent).namespace
    assert left.application_blob_name('users/users.json.gz') != (
        right.application_blob_name('users/users.json.gz')
    )
