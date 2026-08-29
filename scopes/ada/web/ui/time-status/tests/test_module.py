import pytest

from ada.web.ui.time_status import (
    ADA_TIME_STATUS_ASSET_LAYER,
    TimeStatusDefinitionError,
    create_ada_time_status_module,
)


def test_time_status_module_declares_asset_layer_after_core_ui_components() -> None:
    module = create_ada_time_status_module()

    assert module.name == 'ada-time-status'
    assert module.asset_layers == (ADA_TIME_STATUS_ASSET_LAYER,)
    assert ADA_TIME_STATUS_ASSET_LAYER.load_order == 150


def test_time_status_module_publishes_operational_time_zone() -> None:
    default_module = create_ada_time_status_module()
    custom_module = create_ada_time_status_module(time_zone=' America/Punta_Arenas ')

    assert default_module.index.runtime_config == {'time_zone': 'America/Santiago'}
    assert custom_module.index.runtime_config == {'time_zone': 'America/Punta_Arenas'}


@pytest.mark.parametrize('value', ['', '   ', 'America Santiago', '../Santiago'])
def test_time_status_module_rejects_invalid_time_zone_format(value: str) -> None:
    with pytest.raises(TimeStatusDefinitionError, match='time zone has an invalid format'):
        create_ada_time_status_module(time_zone=value)
