from dataclasses import dataclass

import pytest

from ada.configuration.tools import (
    ProcessLayoutRole,
    ToolComponent,
    ToolConfigurationKind,
    ToolScope,
    ToolStructure,
    ToolSubcomponent,
)
from ada.web.component_store import (
    ComponentStoreSnapshot,
    ComponentStoreState,
    ComponentStoreValidationError,
    build_empty_component_stores,
)


@dataclass(frozen=True, slots=True)
class ExamplePayload:
    value: int


def _subcomponent(key: str, *, linked_component_keys: tuple[str, ...] = ()) -> ToolSubcomponent:
    return ToolSubcomponent(
        key=key,
        display_name=key.replace('_', ' ').title(),
        linked_component_keys=linked_component_keys,
    )


def test_empty_snapshot_derives_empty_state_without_separate_status_field() -> None:
    snapshot = ComponentStoreSnapshot(
        tool_key='process',
        component_key='main_process',
    )

    assert snapshot.state is ComponentStoreState.EMPTY
    assert snapshot.is_empty is True
    assert snapshot.payload is None


def test_snapshot_with_typed_payload_derives_populated_state() -> None:
    payload = ExamplePayload(value=42)
    snapshot = ComponentStoreSnapshot(
        tool_key='process',
        component_key='main_process',
        payload=payload,
    )

    assert snapshot.state is ComponentStoreState.POPULATED
    assert snapshot.is_empty is False
    assert snapshot.payload is payload


def test_snapshot_normalizes_tool_and_component_identity() -> None:
    snapshot = ComponentStoreSnapshot(
        tool_key=' Process ',
        component_key=' Main_Process ',
    )

    assert snapshot.tool_key == 'process'
    assert snapshot.component_key == 'main_process'


def test_snapshot_rejects_invalid_identity() -> None:
    with pytest.raises(
        ComponentStoreValidationError,
        match='Component Store component key has an invalid format',
    ):
        ComponentStoreSnapshot(
            tool_key='process',
            component_key='invalid-key',
        )


def test_process_with_four_subcomponents_builds_one_empty_store() -> None:
    structure = ToolStructure(
        tool_key='mine_process',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.MINE,
        components=(
            ToolComponent(
                key='mine',
                display_name='Mine',
                layout_role=ProcessLayoutRole.CENTER,
                subcomponents=(
                    _subcomponent('phase_1'),
                    _subcomponent('phase_2'),
                    _subcomponent('phase_3'),
                    _subcomponent('phase_4'),
                ),
            ),
        ),
    )

    stores = build_empty_component_stores(structure)

    assert stores == (
        ComponentStoreSnapshot(
            tool_key='mine_process',
            component_key='mine',
        ),
    )
    assert all(store.state is ComponentStoreState.EMPTY for store in stores)


def test_integrated_operations_builds_one_store_per_component_in_structure_order() -> None:
    structure = ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='carguio',
                display_name='Carguío',
                scope=ToolScope.MINE,
                subcomponents=(
                    _subcomponent(
                        'gestion_turno',
                        linked_component_keys=('transporte',),
                    ),
                ),
            ),
            ToolComponent(
                key='transporte',
                display_name='Transporte',
                scope=ToolScope.MINE,
                subcomponents=(_subcomponent('transporte_global'),),
            ),
        ),
    )

    stores = build_empty_component_stores(structure)

    assert tuple(store.component_key for store in stores) == (
        'carguio',
        'transporte',
    )
    assert len(stores) == len(structure.components)
    assert all(store.tool_key == structure.tool_key for store in stores)
    assert all(store.state is ComponentStoreState.EMPTY for store in stores)


def test_linked_subcomponent_does_not_create_extra_store() -> None:
    structure = ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='carguio',
                display_name='Carguío',
                scope=ToolScope.MINE,
                subcomponents=(
                    _subcomponent(
                        'shared_status',
                        linked_component_keys=('transporte',),
                    ),
                ),
            ),
            ToolComponent(
                key='transporte',
                display_name='Transporte',
                scope=ToolScope.MINE,
                subcomponents=(_subcomponent('own_status'),),
            ),
        ),
    )

    stores = build_empty_component_stores(structure)

    assert {store.component_key for store in stores} == {'carguio', 'transporte'}
    assert all(store.component_key != 'shared_status' for store in stores)


def test_strategic_uses_same_generic_component_store_projection() -> None:
    structure = ToolStructure(
        tool_key='strategic',
        kind=ToolConfigurationKind.STRATEGIC,
        components=(
            ToolComponent(
                key='overview',
                display_name='Overview',
            ),
        ),
    )

    stores = build_empty_component_stores(structure)

    assert stores == (
        ComponentStoreSnapshot(
            tool_key='strategic',
            component_key='overview',
        ),
    )


def test_builder_rejects_non_tool_structure() -> None:
    with pytest.raises(
        ComponentStoreValidationError,
        match='Tool Structure contract is invalid',
    ):
        build_empty_component_stores(object())  # type: ignore[arg-type]
