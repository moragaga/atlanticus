from importlib.resources import files

from ada.web.application.integrated_operations.modules.dashboard.module import (
    create_dashboard_module,
)
from ada.web.ui.card_display import ADA_CARD_DISPLAY_ASSET_LAYER


def test_dashboard_presentation_javascript_is_packaged() -> None:
    resources = files('ada.web.application.integrated_operations.modules.dashboard').joinpath(
        'resources/js'
    )

    assert resources.joinpath('js.list').read_text(encoding='utf-8').splitlines() == [
        '10_presentation.js'
    ]
    assert resources.joinpath('10_presentation.js').is_file()


def test_dashboard_loads_reusable_card_display_assets() -> None:
    module = create_dashboard_module(None)

    assert module.asset_layers[0] is ADA_CARD_DISPLAY_ASSET_LAYER
