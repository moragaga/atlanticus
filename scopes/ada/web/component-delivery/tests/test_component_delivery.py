from dataclasses import dataclass

import pytest

from ada.web.component_delivery import (
    ComponentDelivery,
    ComponentDeliveryValidationError,
    collect_component_deliveries,
)
from ada.web.component_store import ComponentStoreSnapshot, ComponentStoreState


@dataclass(frozen=True, slots=True)
class ExamplePayload:
    value: int


def _empty_store(component_key: str, *, tool_key: str = 'tool') -> ComponentStoreSnapshot:
    return ComponentStoreSnapshot(tool_key=tool_key, component_key=component_key)


def test_no_deliveries_preserves_existing_empty_stores() -> None:
    stores = (_empty_store('first'), _empty_store('second'))

    result = collect_component_deliveries(stores, ())

    assert result == stores
    assert all(store.state is ComponentStoreState.EMPTY for store in result)


def test_matching_delivery_populates_only_existing_target() -> None:
    stores = (_empty_store('first'), _empty_store('second'))
    payload = ExamplePayload(value=42)

    result = collect_component_deliveries(
        stores,
        (ComponentDelivery(tool_key='tool', component_key='second', payload=payload),),
    )

    assert result[0] is stores[0]
    assert result[0].state is ComponentStoreState.EMPTY
    assert result[1].tool_key == 'tool'
    assert result[1].component_key == 'second'
    assert result[1].payload is payload
    assert result[1].state is ComponentStoreState.POPULATED


def test_store_order_is_preserved_when_delivery_order_differs() -> None:
    stores = (_empty_store('first'), _empty_store('second'))

    result = collect_component_deliveries(
        stores,
        (
            ComponentDelivery(tool_key='tool', component_key='second', payload='B'),
            ComponentDelivery(tool_key='tool', component_key='first', payload='A'),
        ),
    )

    assert tuple(store.component_key for store in result) == ('first', 'second')
    assert tuple(store.payload for store in result) == ('A', 'B')


def test_unknown_component_delivery_target_is_rejected() -> None:
    stores = (_empty_store('existing'),)

    with pytest.raises(
        ComponentDeliveryValidationError,
        match="Unknown Component Store delivery target: 'tool'/'unknown'",
    ):
        collect_component_deliveries(
            stores,
            (ComponentDelivery(tool_key='tool', component_key='unknown', payload='value'),),
        )


def test_wrong_tool_delivery_target_is_rejected() -> None:
    stores = (_empty_store('component', tool_key='tool_a'),)

    with pytest.raises(
        ComponentDeliveryValidationError,
        match="Unknown Component Store delivery target: 'tool_b'/'component'",
    ):
        collect_component_deliveries(
            stores,
            (ComponentDelivery(tool_key='tool_b', component_key='component', payload='value'),),
        )


def test_duplicate_deliveries_are_rejected_instead_of_last_write_wins() -> None:
    stores = (_empty_store('component'),)

    with pytest.raises(
        ComponentDeliveryValidationError,
        match="Duplicate Component Delivery address: 'tool'/'component'",
    ):
        collect_component_deliveries(
            stores,
            (
                ComponentDelivery(tool_key='tool', component_key='component', payload='first'),
                ComponentDelivery(tool_key='tool', component_key='component', payload='second'),
            ),
        )


def test_duplicate_store_addresses_are_rejected() -> None:
    stores = (_empty_store('component'), _empty_store('component'))

    with pytest.raises(
        ComponentDeliveryValidationError,
        match="Duplicate Component Store address: 'tool'/'component'",
    ):
        collect_component_deliveries(stores, ())


def test_delivery_payload_must_be_present() -> None:
    with pytest.raises(
        ComponentDeliveryValidationError,
        match='Component Delivery payload must not be None',
    ):
        ComponentDelivery(tool_key='tool', component_key='component', payload=None)


def test_delivery_identity_is_normalized() -> None:
    delivery = ComponentDelivery(
        tool_key=' Tool ',
        component_key=' Component ',
        payload='value',
    )

    assert delivery.tool_key == 'tool'
    assert delivery.component_key == 'component'


def test_missing_delivery_does_not_clear_previously_populated_store() -> None:
    payload = ExamplePayload(value=7)
    populated = ComponentStoreSnapshot(
        tool_key='tool',
        component_key='component',
        payload=payload,
    )

    result = collect_component_deliveries((populated,), ())

    assert result == (populated,)
    assert result[0] is populated
    assert result[0].payload is payload
    assert result[0].state is ComponentStoreState.POPULATED


def test_empty_store_set_accepts_no_deliveries() -> None:
    assert collect_component_deliveries((), ()) == ()
