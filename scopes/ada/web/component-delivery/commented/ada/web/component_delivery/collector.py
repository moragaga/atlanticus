from collections.abc import Iterable
from dataclasses import replace

from ada.web.component_delivery.errors import ComponentDeliveryValidationError
from ada.web.component_delivery.models import ComponentDelivery
from ada.web.component_store import ComponentStoreSnapshot


def collect_component_deliveries(
    stores: Iterable[ComponentStoreSnapshot],
    deliveries: Iterable[ComponentDelivery],
) -> tuple[ComponentStoreSnapshot, ...]:
    # Materializamos ambos iterables una vez para validar de manera determinista.
    store_values = tuple(stores)
    delivery_values = tuple(deliveries)
    # Los Stores existentes son la autoridad de destinos válidos.
    store_addresses = _validate_stores(store_values)
    # Ninguna entrega puede introducir una dirección que no exista previamente.
    delivery_by_address = _validate_deliveries(delivery_values, store_addresses)
    # Se conserva exactamente el orden de entrada de los Stores.
    return tuple(
        _hydrate_store(store, delivery_by_address.get(_address(store)))
        for store in store_values
    )


def _validate_stores(
    stores: tuple[ComponentStoreSnapshot, ...],
) -> set[tuple[str, str]]:
    addresses: set[tuple[str, str]] = set()
    for store in stores:
        if not isinstance(store, ComponentStoreSnapshot):
            raise ComponentDeliveryValidationError(
                'Component Stores must contain ComponentStoreSnapshot values'
            )
        address = _address(store)
        # Dos Stores con la misma identidad harían ambiguo el destino del delivery.
        if address in addresses:
            raise ComponentDeliveryValidationError(
                f'Duplicate Component Store address: {address[0]!r}/{address[1]!r}'
            )
        addresses.add(address)
    return addresses


def _validate_deliveries(
    deliveries: tuple[ComponentDelivery, ...],
    store_addresses: set[tuple[str, str]],
) -> dict[tuple[str, str], ComponentDelivery]:
    by_address: dict[tuple[str, str], ComponentDelivery] = {}
    for delivery in deliveries:
        if not isinstance(delivery, ComponentDelivery):
            raise ComponentDeliveryValidationError(
                'Component deliveries must contain ComponentDelivery values'
            )
        address = _address(delivery)
        # No usamos last-write-wins porque ocultaría una entrega ambigua.
        if address in by_address:
            raise ComponentDeliveryValidationError(
                f'Duplicate Component Delivery address: {address[0]!r}/{address[1]!r}'
            )
        # El Collector jamás crea un Store porque apareció información nueva.
        if address not in store_addresses:
            raise ComponentDeliveryValidationError(
                f'Unknown Component Store delivery target: {address[0]!r}/{address[1]!r}'
            )
        by_address[address] = delivery
    return by_address


def _hydrate_store(
    store: ComponentStoreSnapshot,
    delivery: ComponentDelivery | None,
) -> ComponentStoreSnapshot:
    # Ausencia de delivery no implica limpiar, expirar ni degradar el Store.
    if delivery is None:
        return store
    # Snapshot inmutable: se reemplaza sólo el payload y se conserva la identidad.
    return replace(store, payload=delivery.payload)


def _address(value: ComponentStoreSnapshot | ComponentDelivery) -> tuple[str, str]:
    return value.tool_key, value.component_key
