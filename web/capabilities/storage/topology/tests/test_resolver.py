from __future__ import annotations

from dataclasses import dataclass

import pytest

from atlanticus.web.storage.topology import (
    ForbiddenStorageResourceOverrideError,
    MissingStorageConnectionBindingError,
    StoragePhysicalResourceConflictError,
    StorageResourceContract,
    StorageResourceDeclarationConflictError,
    StorageResourceOverride,
    StorageResourceOverrideConflictError,
    StorageResourceOverrideField,
    UnknownStorageResourceOverrideError,
    resolve_storage_plan,
)


@dataclass(frozen=True, slots=True)
class ExampleTopology:
    partition_key: str
    ttl: int | None = None


def _contract(
    logical_id: str,
    *,
    owner: str = 'users',
    provider: str = 'cosmos',
    connection_ref: str | None = 'primary',
    physical_name: str | None = None,
    topology: ExampleTopology | None = None,
    allowed_overrides: frozenset[StorageResourceOverrideField] = frozenset(),
) -> StorageResourceContract[ExampleTopology]:
    return StorageResourceContract(
        logical_id=logical_id,
        owner=owner,
        provider=provider,
        default_connection_ref=connection_ref,
        default_physical_name=physical_name or logical_id.replace('.', '-'),
        topology=topology or ExampleTopology('/id'),
        allowed_overrides=allowed_overrides,
    )


def test_resolution_is_deterministic_and_keeps_topology_opaque() -> None:
    users_topology = ExampleTopology('/id')
    users = _contract('users.runtime', topology=users_topology)
    support = _contract('users-support.runtime', owner='users-support')

    plan = resolve_storage_plan([users, support])
    reverse_plan = resolve_storage_plan([support, users])

    assert [resource.logical_id for resource in plan.resources] == [
        'users-support.runtime',
        'users.runtime',
    ]
    assert plan == reverse_plan
    users_resource = next(
        resource for resource in plan.resources if resource.logical_id == 'users.runtime'
    )
    assert users_resource.topology is users_topology


def test_identical_declarations_are_deduplicated() -> None:
    contract = _contract('users.runtime')

    plan = resolve_storage_plan([contract, contract])

    assert len(plan.resources) == 1


def test_incompatible_duplicate_declarations_fail() -> None:
    with pytest.raises(StorageResourceDeclarationConflictError):
        resolve_storage_plan(
            [
                _contract('users.runtime', physical_name='users-runtime'),
                _contract('users.runtime', physical_name='other-users-runtime'),
            ]
        )


def test_allowed_overrides_replace_only_declared_binding_fields() -> None:
    contract = _contract(
        'users.runtime',
        connection_ref=None,
        allowed_overrides=frozenset(
            {
                StorageResourceOverrideField.CONNECTION_REF,
                StorageResourceOverrideField.PHYSICAL_NAME,
            }
        ),
    )

    plan = resolve_storage_plan(
        [contract],
        [
            StorageResourceOverride(
                logical_id='users.runtime',
                connection_ref='users-primary',
                physical_name='users-runtime-prod',
            )
        ],
    )

    resource = plan.resources[0]
    assert resource.connection_ref == 'users-primary'
    assert resource.physical_name == 'users-runtime-prod'
    assert resource.owner == 'users'
    assert resource.provider == 'cosmos'
    assert resource.topology == ExampleTopology('/id')


def test_forbidden_override_fails_even_when_value_matches_default() -> None:
    contract = _contract('users.runtime', connection_ref='primary')

    with pytest.raises(ForbiddenStorageResourceOverrideError) as captured:
        resolve_storage_plan(
            [contract],
            [StorageResourceOverride(logical_id='users.runtime', connection_ref='primary')],
        )

    assert captured.value.field_name == 'connection_ref'


def test_unknown_override_fails() -> None:
    with pytest.raises(UnknownStorageResourceOverrideError):
        resolve_storage_plan(
            [_contract('users.runtime')],
            [StorageResourceOverride(logical_id='missing.runtime', connection_ref='primary')],
        )


def test_conflicting_duplicate_overrides_fail() -> None:
    contract = _contract(
        'users.runtime',
        allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
    )

    with pytest.raises(StorageResourceOverrideConflictError):
        resolve_storage_plan(
            [contract],
            [
                StorageResourceOverride(logical_id='users.runtime', connection_ref='primary-a'),
                StorageResourceOverride(logical_id='users.runtime', connection_ref='primary-b'),
            ],
        )


def test_identical_duplicate_overrides_are_deduplicated() -> None:
    contract = _contract(
        'users.runtime',
        allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
    )
    override = StorageResourceOverride(logical_id='users.runtime', connection_ref='primary-a')

    plan = resolve_storage_plan([contract], [override, override])

    assert plan.resources[0].connection_ref == 'primary-a'


def test_missing_required_connection_binding_fails_before_resolution_completes() -> None:
    with pytest.raises(MissingStorageConnectionBindingError):
        resolve_storage_plan([_contract('users.runtime', connection_ref=None)])


def test_two_logical_resources_cannot_resolve_to_same_physical_resource() -> None:
    with pytest.raises(StoragePhysicalResourceConflictError) as captured:
        resolve_storage_plan(
            [
                _contract('users.runtime', physical_name='shared-runtime'),
                _contract(
                    'users-support.runtime',
                    owner='users-support',
                    physical_name='shared-runtime',
                ),
            ]
        )

    assert captured.value.provider == 'cosmos'
    assert captured.value.connection_ref == 'primary'
    assert captured.value.physical_name == 'shared-runtime'


def test_same_physical_name_is_valid_across_different_connections() -> None:
    plan = resolve_storage_plan(
        [
            _contract('users.runtime', connection_ref='primary-a', physical_name='runtime'),
            _contract(
                'users-support.runtime',
                owner='users-support',
                connection_ref='primary-b',
                physical_name='runtime',
            ),
        ]
    )

    assert len(plan.resources) == 2
