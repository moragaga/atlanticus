from __future__ import annotations

import pytest

from ada.web.configuration import ConfigurationMutationState, ConfigurationMutationStatus


def test_busy_mutation_blocks_only_its_item() -> None:
    state = ConfigurationMutationState(
        status=ConfigurationMutationStatus.SAVING,
        item_key='kpi_a',
    )

    assert state.busy
    assert state.blocks('kpi_a')
    assert not state.blocks('kpi_b')


def test_conflict_requires_item_identity() -> None:
    with pytest.raises(ValueError, match='item key'):
        ConfigurationMutationState(status=ConfigurationMutationStatus.CONFLICT)
