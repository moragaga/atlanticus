from __future__ import annotations

from dataclasses import replace

import pytest

from ada.web.application.generic.manager_persistence import (
    ManagerBlobResource,
    ManagerPersistenceConnections,
    ManagerPersistenceResources,
    compose_durable_manager_stores,
    resolve_manager_cosmos_plan,
)
from ada.web.storage.namespace import AdaStorageNamespace
from atlanticus.connectivity.storage import StorageBlobNotFoundError
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.source.models import SourceKey
from atlanticus.web.storage.topology import (
    MissingStorageConnectionBindingError,
    ResolvedStoragePlan,
    StorageResourceOverride,
)


class MissingStorage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def get_properties(self, *, container_name: str, blob_name: str):
        self.calls.append((container_name, blob_name))
        raise StorageBlobNotFoundError('Not present')


class EmptyCosmos:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def find_item(self, **kwargs):
        self.calls.append(kwargs)
        return None


def _resources() -> ManagerPersistenceResources:
    return ManagerPersistenceResources(
        application_source=ManagerBlobResource('application-storage', 'configuration'),
        tool_source=ManagerBlobResource('tool-storage', 'configuration'),
        users_registry=ManagerBlobResource('users-storage', 'users'),
        cosmos_plan=resolve_manager_cosmos_plan(
            (
                StorageResourceOverride('navigation.projection', connection_ref='ada-cosmos'),
                StorageResourceOverride('users.support', connection_ref='ada-cosmos'),
                StorageResourceOverride('ada.tools.projection', connection_ref='ada-cosmos'),
                StorageResourceOverride(
                    'ada.kpis.registry.projection', connection_ref='ada-cosmos'
                ),
                StorageResourceOverride(
                    'ada.kpis.definition.projection', connection_ref='ada-cosmos'
                ),
                StorageResourceOverride('users.runtime', connection_ref='ada-cosmos'),
            )
        ),
    )


def _connections():
    app = MissingStorage()
    tool = MissingStorage()
    users = MissingStorage()
    ada_cosmos = EmptyCosmos()
    return (
        ManagerPersistenceConnections(
            storage={
                'application-storage': app,
                'tool-storage': tool,
                'users-storage': users,
            },
            cosmos={'ada-cosmos': ada_cosmos},
        ),
        (app, tool, users, ada_cosmos),
    )


def _namespace() -> AdaStorageNamespace:
    return AdaStorageNamespace(application_namespace='ada-site', tool_namespace='plant')


def test_factory_is_lazy_and_preserves_independent_source_namespaces():
    connections, (app, tool, users, ada_cosmos) = _connections()
    stores = compose_durable_manager_stores(
        namespace=_namespace(), resources=_resources(), connections=connections
    )
    assert all(not storage.calls for storage in (app, tool, users))
    assert not ada_cosmos.calls

    assert stores.navigation_source.get_current(SourceKey('navigation')).current is None
    assert stores.profiles_source.get_current(SourceKey('profiles-configuration')).current is None
    assert stores.access_source.get_current(SourceKey('ada-access')).current is None
    assert stores.tools_source.get_current(SourceKey('tools')).current is None
    assert stores.kpi_registry_source.get_current(SourceKey('kpis')).current is None
    assert stores.kpi_definitions_source.get_current(SourceKey('kpi-definitions')).current is None

    assert app.calls == [
        ('configuration', 'ada-site/sources/bmF2aWdhdGlvbg/manifest.json'),
        ('configuration', 'ada-site/sources/cHJvZmlsZXMtY29uZmlndXJhdGlvbg/manifest.json'),
        ('configuration', 'ada-site/sources/YWRhLWFjY2Vzcw/manifest.json'),
    ]
    assert tool.calls == [
        ('configuration', 'ada-site/plant/sources/dG9vbHM/manifest.json'),
        ('configuration', 'ada-site/plant/sources/a3Bpcw/manifest.json'),
        ('configuration', 'ada-site/plant/sources/a3BpLWRlZmluaXRpb25z/manifest.json'),
    ]
    assert not users.calls


def test_one_cosmos_connection_keeps_navigation_outside_shared_users_support():
    connections, (_app, _tool, _users, ada_cosmos) = _connections()
    stores = compose_durable_manager_stores(
        namespace=_namespace(), resources=_resources(), connections=connections
    )
    assert stores.navigation.get_active(SourceKey('navigation')) is None
    assert stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY) is None
    assert stores.access.get_active(SourceKey('ada-access')) is None
    assert stores.tools.get_active(SourceKey('tools')) is None
    assert stores.kpi_registry.get_active(SourceKey('kpis')) is None
    assert stores.kpi_definitions.get_active(SourceKey('kpi-definitions')) is None
    assert (
        stores.users_promoted.resolve(
            AuthenticatedIdentity(provider_key='entra', issuer='issuer', subject_id='subject')
        )
        is None
    )

    assert [call['container_name'] for call in ada_cosmos.calls] == [
        'navigation-projection',
        'users-support',
        'users-support',
        'ada-tool-projection',
        'ada-kpi-registry-projection',
        'ada-kpi-definition-projection',
        'users-runtime',
    ]
    navigation = ada_cosmos.calls[0]
    support = ada_cosmos.calls[1:3]
    assert navigation['container_name'] != support[0]['container_name']
    assert navigation['partition_key'] == 'navigation'
    assert {resource.logical_id for resource in _resources().cosmos_plan.resources} == {
        'navigation.projection',
        'users.support',
        'users.runtime',
        'ada.tools.projection',
        'ada.kpis.registry.projection',
        'ada.kpis.definition.projection',
    }
    assert len({(call['item_id'], call['partition_key']) for call in support}) == 2
    assert all(call['partition_key'] != 'ada-site/plant' for call in support)


def test_users_registry_is_application_global_not_tool_scoped():
    connections, (_app, _tool, users, _ada_cosmos) = _connections()
    stores = compose_durable_manager_stores(
        namespace=_namespace(), resources=_resources(), connections=connections
    )
    assert stores.users_registry.load().users == ()
    assert users.calls == [('users', 'ada-site/users/users.json.gz')]


def test_missing_named_connection_fails_before_any_provider_io():
    connections, (app, tool, users, ada_cosmos) = _connections()
    connections = replace(connections, cosmos={})
    with pytest.raises(ValueError, match='ada-cosmos'):
        compose_durable_manager_stores(
            namespace=_namespace(), resources=_resources(), connections=connections
        )
    assert all(not client.calls for client in (app, tool, users, ada_cosmos))


def test_invalid_resource_bindings_are_rejected_explicitly():
    with pytest.raises(MissingStorageConnectionBindingError):
        resolve_manager_cosmos_plan(())
    with pytest.raises(ValueError, match='container name'):
        ManagerBlobResource('storage', ' container ')
    with pytest.raises(TypeError, match='Blob resource'):
        replace(_resources(), users_registry=object())


def test_different_tool_namespaces_produce_distinct_source_paths():
    connections, (_app, tool, _users, _ada_cosmos) = _connections()
    first = compose_durable_manager_stores(
        namespace=_namespace(), resources=_resources(), connections=connections
    )
    second = compose_durable_manager_stores(
        namespace=AdaStorageNamespace('ada-site', 'mine'),
        resources=_resources(),
        connections=connections,
    )
    first.tools_source.get_current(SourceKey('tools'))
    second.tools_source.get_current(SourceKey('tools'))
    assert tool.calls == [
        ('configuration', 'ada-site/plant/sources/dG9vbHM/manifest.json'),
        ('configuration', 'ada-site/mine/sources/dG9vbHM/manifest.json'),
    ]


def test_tool_projection_addresses_are_namespaced_independently():
    connections, (_app, _tool, _users, ada_cosmos) = _connections()
    plant = compose_durable_manager_stores(
        namespace=_namespace(), resources=_resources(), connections=connections
    )
    mine = compose_durable_manager_stores(
        namespace=AdaStorageNamespace('ada-site', 'mine'),
        resources=_resources(),
        connections=connections,
    )
    plant.tools.get_active(SourceKey('tools'))
    mine.tools.get_active(SourceKey('tools'))
    assert ada_cosmos.calls[0]['item_id'] != ada_cosmos.calls[1]['item_id']
    assert ada_cosmos.calls[0]['partition_key'] != ada_cosmos.calls[1]['partition_key']


def test_external_cosmos_plan_cannot_override_canonical_topology():
    resources = _resources()
    current = resources.cosmos_plan.resources
    tampered = ResolvedStoragePlan(
        resources=(replace(current[0], physical_name='unapproved'), *current[1:])
    )
    with pytest.raises(ValueError, match='topology'):
        replace(resources, cosmos_plan=tampered)


def test_ada_manager_does_not_accept_multiple_cosmos_connections():
    plan = _resources().cosmos_plan
    modified = ResolvedStoragePlan(
        resources=(replace(plan.resources[0], connection_ref='another-db'), *plan.resources[1:])
    )
    with pytest.raises(ValueError, match='one Cosmos connection'):
        replace(_resources(), cosmos_plan=modified)


def test_navigation_plan_uses_its_canonical_physical_resource():
    plan = _resources().cosmos_plan
    resources = {resource.logical_id: resource for resource in plan.resources}
    assert resources['navigation.projection'].physical_name == 'navigation-projection'
    assert resources['users.support'].physical_name == 'users-support'
    assert resources['navigation.projection'].connection_ref == (
        resources['users.support'].connection_ref
    )
    assert resources['navigation.projection'].physical_name != (
        resources['users.support'].physical_name
    )
