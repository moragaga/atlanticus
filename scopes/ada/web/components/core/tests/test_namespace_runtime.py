def test_components_namespace_runtime() -> None:
    import ada.web.components
    from ada.web.components import (
        ComponentDelivery,
        ComponentStoreSnapshot,
        collect_component_deliveries,
    )

    assert ada.web.components.__spec__ is not None
    assert ComponentDelivery is not None
    assert ComponentStoreSnapshot is not None
    assert collect_component_deliveries is not None
