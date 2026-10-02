from copy import deepcopy

import pytest

from ada.kpis.materialization import (
    KpiMaterializationContractError,
    materialize_registry,
    validate_materialized_registry,
    validate_registry_projection,
)
from tests.support import projection


def test_materialization_preserves_projection_and_adds_root_tool_key():
    source = projection()
    materialized = materialize_registry(tool_key='integrated_operations', projection=source)

    assert materialized['tool_key'] == 'integrated_operations'
    assert {key: value for key, value in materialized.items() if key != 'tool_key'} == source
    assert materialized is not source


def test_tool_key_uses_current_tool_contract():
    with pytest.raises(KpiMaterializationContractError, match='tool_key'):
        materialize_registry(tool_key='invalid-tool', projection=projection())


def test_projection_contract_is_strict():
    source = projection()
    source['unexpected'] = True

    with pytest.raises(KpiMaterializationContractError, match='unexpected or missing'):
        validate_registry_projection(source)


def test_materialized_document_must_match_expected_tool():
    document = materialize_registry(tool_key='tool_a', projection=projection())

    with pytest.raises(KpiMaterializationContractError, match='tool_key mismatch'):
        validate_materialized_registry(document, expected_tool_key='tool_b')


def test_binding_contract_requires_at_least_one_destination():
    source = deepcopy(projection())
    source['payload']['bindings'][0]['destination_keys'] = []

    with pytest.raises(KpiMaterializationContractError, match='must not be empty'):
        validate_registry_projection(source)
