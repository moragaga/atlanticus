from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

import pytest

from atlanticus.web.storage.topology import (
    ResolvedStoragePlan,
    ResolvedStorageResource,
    StorageResourceContract,
    StorageResourceOverride,
    StorageResourceOverrideField,
    StorageTopologyConfigurationError,
)


@dataclass(frozen=True, slots=True)
class ExampleTopology:
    partition_key: str


def test_contract_normalizes_allowed_overrides_to_immutable_set() -> None:
    contract = StorageResourceContract(
        logical_id='users.runtime',
        owner='users',
        provider='cosmos',
        default_connection_ref=None,
        default_physical_name='users-runtime',
        topology=ExampleTopology('/id'),
        allowed_overrides=[StorageResourceOverrideField.CONNECTION_REF],
    )

    assert contract.allowed_overrides == frozenset({StorageResourceOverrideField.CONNECTION_REF})
    with pytest.raises(FrozenInstanceError):
        contract.owner = 'other'


def test_override_requires_at_least_one_value() -> None:
    with pytest.raises(
        StorageTopologyConfigurationError,
        match='must set connection_ref or physical_name',
    ):
        StorageResourceOverride(logical_id='users.runtime')


def test_text_fields_reject_surrounding_whitespace() -> None:
    with pytest.raises(StorageTopologyConfigurationError, match='surrounding whitespace'):
        StorageResourceContract(
            logical_id=' users.runtime',
            owner='users',
            provider='cosmos',
            default_connection_ref='primary',
            default_physical_name='users-runtime',
            topology=ExampleTopology('/id'),
        )


def test_resolved_plan_materializes_resources_as_tuple() -> None:
    resource = ResolvedStorageResource(
        logical_id='users.runtime',
        owner='users',
        provider='cosmos',
        connection_ref='primary',
        physical_name='users-runtime',
        topology=ExampleTopology('/id'),
    )

    plan = ResolvedStoragePlan(resources=[resource])

    assert plan.resources == (resource,)
