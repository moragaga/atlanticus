from collections.abc import Iterable

from ada.configuration.tools import ToolStructure
from ada.web.component_store import ComponentStoreSnapshot
from ada.web.operational_render_binding.errors import OperationalRenderBindingError
from ada.web.operational_render_binding.models import (
    OperationalComponentBinding,
    OperationalRenderBinding,
)


def bind_operational_render(
    structure: ToolStructure,
    stores: Iterable[ComponentStoreSnapshot],
) -> OperationalRenderBinding:
    # La topología siempre entra primero: los Stores sólo pueden hidratar lo que ya existe allí.
    if not isinstance(structure, ToolStructure):
        raise OperationalRenderBindingError('Operational render requires ToolStructure')

    store_values = tuple(stores)
    expected_keys = tuple(component.key for component in structure.components)
    expected_key_set = set(expected_keys)
    stores_by_key: dict[str, ComponentStoreSnapshot] = {}

    for store in store_values:
        if not isinstance(store, ComponentStoreSnapshot):
            raise OperationalRenderBindingError(
                'Operational render stores must contain ComponentStoreSnapshot values'
            )
        # Impide cruzar accidentalmente Stores pertenecientes a otra Tool.
        if store.tool_key != structure.tool_key:
            raise OperationalRenderBindingError(
                'Operational render Component Store tool key must match Tool Structure'
            )
        if store.component_key in stores_by_key:
            raise OperationalRenderBindingError(
                f'Duplicate Operational Render Component Store: {store.component_key!r}'
            )
        # Un Store extra no crea un Component nuevo ni amplía la estructura.
        if store.component_key not in expected_key_set:
            raise OperationalRenderBindingError(
                f'Unknown Operational Render Component Store: {store.component_key!r}'
            )
        stores_by_key[store.component_key] = store

    # Cada Component estructural debe conservar su Store aunque todavía no tenga payload.
    missing_key = next((key for key in expected_keys if key not in stores_by_key), None)
    if missing_key is not None:
        raise OperationalRenderBindingError(
            f'Missing Operational Render Component Store: {missing_key!r}'
        )

    # Se reconstruye el orden desde ToolStructure, no desde la secuencia recibida de Stores.
    return OperationalRenderBinding(
        structure=structure,
        components=tuple(
            OperationalComponentBinding(
                component=component,
                store=stores_by_key[component.key],
            )
            for component in structure.components
        ),
    )
