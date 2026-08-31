from dataclasses import FrozenInstanceError

import pytest

from ada.configuration.tool_sources import ToolSourceConsumption


def test_contract_is_immutable() -> None:
    consumption = ToolSourceConsumption(tool_key='process', source_keys=('pi',))

    with pytest.raises(FrozenInstanceError):
        consumption.tool_key = 'other'  # type: ignore[misc]


def test_contract_has_no_role_or_ui_fields() -> None:
    fields = ToolSourceConsumption.__dataclass_fields__

    assert tuple(fields) == ('tool_key', 'source_keys')
    assert 'optional' not in fields
    assert 'role' not in fields
    assert 'show_in_summary' not in fields
    assert 'show_in_popover' not in fields
    assert 'affects_overlay' not in fields


def test_contract_module_has_no_control_or_informational_catalog() -> None:
    import ada.configuration.tool_sources.consumption as models

    source = models.__loader__.get_source(models.__name__) or ''

    assert 'CONTROL' not in source
    assert 'INFORMATIONAL' not in source
    assert '_CONTROL_SOURCE_KEYS' not in source
    assert 'dispatch' not in source
    assert 'blockgrade' not in source


def test_contract_module_has_no_transport_or_storage_dependency() -> None:
    import ada.configuration.tool_sources.consumption as models

    source = (models.__loader__.get_source(models.__name__) or '').casefold()

    assert 'azure' not in source
    assert 'cosmos' not in source
    assert 'sharepoint' not in source
    assert 'collector' not in source
