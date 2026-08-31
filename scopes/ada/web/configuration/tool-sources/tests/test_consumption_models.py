from types import MappingProxyType

import pytest

from ada.configuration.tool_sources import (
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
)


def test_contract_normalizes_tool_key_and_source_keys() -> None:
    consumption = ToolSourceConsumption(
        tool_key=' Integrated_Operations ',
        source_keys=(' PI ', 'Dispatch'),
    )

    assert consumption.tool_key == 'integrated_operations'
    assert consumption.source_keys == ('pi', 'dispatch')


def test_contract_preserves_declared_source_order() -> None:
    consumption = ToolSourceConsumption(
        tool_key='process',
        source_keys=('blockgrade', 'pi', 'dispatch'),
    )

    assert consumption.source_keys == ('blockgrade', 'pi', 'dispatch')


def test_contract_accepts_list_input_and_freezes_it_as_tuple() -> None:
    consumption = ToolSourceConsumption(
        tool_key='process',
        source_keys=['pi', 'blockgrade'],  # type: ignore[arg-type]
    )

    assert consumption.source_keys == ('pi', 'blockgrade')
    assert isinstance(consumption.source_keys, tuple)


def test_contract_allows_empty_source_membership() -> None:
    consumption = ToolSourceConsumption(tool_key='generic_tool')

    assert consumption.source_keys == ()


def test_contract_accepts_source_without_global_catalog_entry() -> None:
    consumption = ToolSourceConsumption(
        tool_key='future_tool',
        source_keys=('future_source_2',),
    )

    assert consumption.source_keys == ('future_source_2',)


def test_contract_rejects_duplicate_sources() -> None:
    with pytest.raises(ToolSourceConsumptionValidationError, match='must be unique'):
        ToolSourceConsumption(tool_key='process', source_keys=('pi', 'pi'))


def test_contract_rejects_duplicate_sources_after_normalization() -> None:
    with pytest.raises(ToolSourceConsumptionValidationError, match='must be unique'):
        ToolSourceConsumption(tool_key='process', source_keys=('PI', ' pi '))


def test_contract_rejects_invalid_tool_key() -> None:
    for tool_key in ('', ' ', '1process', 'process-name', 'process name'):
        with pytest.raises(
            ToolSourceConsumptionValidationError,
            match='Tool key has an invalid format',
        ):
            ToolSourceConsumption(tool_key=tool_key)


def test_contract_rejects_invalid_source_key() -> None:
    for source_key in ('', ' ', '1pi', 'pi-source', 'pi source'):
        with pytest.raises(
            ToolSourceConsumptionValidationError,
            match='Source key has an invalid format',
        ):
            ToolSourceConsumption(tool_key='process', source_keys=(source_key,))


def test_contract_rejects_non_string_tool_key() -> None:
    with pytest.raises(ToolSourceConsumptionValidationError, match='Tool key must be a string'):
        ToolSourceConsumption(tool_key=1)  # type: ignore[arg-type]


def test_contract_rejects_non_string_source_key() -> None:
    with pytest.raises(ToolSourceConsumptionValidationError, match='Source key must be a string'):
        ToolSourceConsumption(tool_key='process', source_keys=('pi', 1))  # type: ignore[arg-type]


def test_contract_rejects_string_as_source_collection() -> None:
    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match='must be a collection of source keys',
    ):
        ToolSourceConsumption(tool_key='process', source_keys='pi')  # type: ignore[arg-type]


def test_consumes_reports_membership_and_rejects_invalid_identity() -> None:
    consumption = ToolSourceConsumption(tool_key='process', source_keys=('pi', 'blockgrade'))

    assert consumption.consumes('PI') is True
    assert consumption.consumes('dispatch') is False
    with pytest.raises(
        ToolSourceConsumptionValidationError, match='Source key has an invalid format'
    ):
        consumption.consumes('invalid source')


def test_document_roundtrip_preserves_contract() -> None:
    consumption = ToolSourceConsumption(
        tool_key='integrated_operations',
        source_keys=('pi', 'dispatch', 'blockgrade'),
    )

    restored = ToolSourceConsumption.from_document(consumption.to_document())

    assert restored == consumption


def test_document_shape_uses_tool_key_and_source_keys_only() -> None:
    document = ToolSourceConsumption(
        tool_key='process',
        source_keys=('pi', 'blockgrade'),
    ).to_document()

    assert document == {
        'tool_key': 'process',
        'source_keys': ['pi', 'blockgrade'],
    }


def test_document_reader_accepts_mapping_contract() -> None:
    document = MappingProxyType(
        {
            'tool_key': 'process',
            'source_keys': ['pi'],
        }
    )

    assert ToolSourceConsumption.from_document(document) == ToolSourceConsumption(
        tool_key='process',
        source_keys=('pi',),
    )


def test_document_reader_rejects_missing_required_fields() -> None:
    for document in ({'source_keys': ['pi']}, {'tool_key': 'process'}):
        with pytest.raises(ToolSourceConsumptionValidationError, match='contract is invalid'):
            ToolSourceConsumption.from_document(document)


def test_document_reader_rejects_non_list_source_keys() -> None:
    with pytest.raises(ToolSourceConsumptionValidationError, match='contract is invalid'):
        ToolSourceConsumption.from_document(
            {
                'tool_key': 'process',
                'source_keys': ('pi',),
            }
        )
