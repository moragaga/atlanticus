import pytest

from ada_command_center.alarms.materialization import (
    EvaluatorQualificationCatalog,
    EvaluatorQualificationKey,
    ToolReconciliationQualification,
)


def test_tool_reconciliation_qualification_normalizes_and_queries_green_tools() -> None:
    qualification = ToolReconciliationQualification(
        green_tool_keys=('tool-z', 'tool-a'),
    )
    assert qualification.green_tool_keys == ('tool-a', 'tool-z')
    assert qualification.is_green('tool-a')
    assert not qualification.is_green('tool-missing')


def test_tool_reconciliation_qualification_rejects_ambiguous_keys() -> None:
    with pytest.raises(ValueError, match='duplicates'):
        ToolReconciliationQualification(
            green_tool_keys=('tool-a', 'tool-a'),
        )
    with pytest.raises(ValueError, match='tool_key'):
        ToolReconciliationQualification(
            green_tool_keys=('',),
        )


def test_evaluator_qualification_catalog_uses_family_and_evaluator_pair() -> None:
    catalog = EvaluatorQualificationCatalog(
        qualified_keys=(
            EvaluatorQualificationKey('plant', 'threshold'),
            EvaluatorQualificationKey('mill', 'threshold'),
        ),
    )
    assert catalog.qualified_keys == (
        EvaluatorQualificationKey('mill', 'threshold'),
        EvaluatorQualificationKey('plant', 'threshold'),
    )
    assert catalog.is_qualified('mill', 'threshold')
    assert not catalog.is_qualified('mill', 'rate_of_change')


def test_evaluator_qualification_catalog_rejects_duplicate_keys() -> None:
    key = EvaluatorQualificationKey('mill', 'threshold')
    with pytest.raises(ValueError, match='duplicates'):
        EvaluatorQualificationCatalog(qualified_keys=(key, key))


def test_qualification_keys_require_non_empty_contract_values() -> None:
    with pytest.raises(ValueError, match='family_key'):
        EvaluatorQualificationKey('', 'threshold')
    with pytest.raises(ValueError, match='evaluator_key'):
        EvaluatorQualificationKey('mill', '')
    with pytest.raises(ValueError, match='tool_key'):
        ToolReconciliationQualification(green_tool_keys=()).is_green('')
