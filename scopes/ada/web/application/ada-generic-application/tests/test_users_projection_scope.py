from ada.web.application.generic.manager_deployment import resolve_durable_manager_configuration
from ada.web.application.generic.settings import AdaGenericSettings


def _settings(tool_namespace):
    return AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_PERSISTENCE_MODE': 'durable',
            'ADA_APPLICATION_NAMESPACE': 'shared-users',
            'ADA_TOOL_NAMESPACE': tool_namespace,
            'ADA_STORAGE_CONTAINER_NAME': 'configuration',
            'ADA_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COSMOS_ENDPOINT': 'http://localhost:8081',
            'ADA_COSMOS_KEY': 'test-only',
            'ADA_COSMOS_DATABASE_NAME': 'shared-database',
        }
    )


def test_two_tools_share_global_identity_registry_but_not_tool_user_artifacts():
    first = resolve_durable_manager_configuration(_settings('mine'))
    second = resolve_durable_manager_configuration(_settings('flotation'))
    assert first.namespace.application_prefix == second.namespace.application_prefix
    assert first.namespace.application_blob_name('users/users.json.gz') == (
        second.namespace.application_blob_name('users/users.json.gz')
    )
    assert first.namespace.scope_blob_name('users/memberships.json.gz') != (
        second.namespace.scope_blob_name('users/memberships.json.gz')
    )
    assert first.namespace.scope_blob_name('users/recovery/snapshots') != (
        second.namespace.scope_blob_name('users/recovery/snapshots')
    )


def test_independent_application_namespace_has_separate_global_identity_registry():
    shared = _settings('mine')
    independent = shared.model_copy(update={'application_namespace': 'independent-users'})
    left = resolve_durable_manager_configuration(shared).namespace
    right = resolve_durable_manager_configuration(independent).namespace
    assert left.application_blob_name('users/users.json.gz') != (
        right.application_blob_name('users/users.json.gz')
    )
