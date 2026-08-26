from pathlib import Path

from ada.web.ui.core import ADA_UI_ASSET_LAYER, create_ada_ui_module


def test_ada_ui_core_declares_foundational_assets_only() -> None:
    module = create_ada_ui_module()

    assert module.name == 'ada-ui'
    assert module.asset_layers == (ADA_UI_ASSET_LAYER,)
    assert ADA_UI_ASSET_LAYER.load_order == 100
    assert ADA_UI_ASSET_LAYER.package == 'ada.web.ui.core'
    assert module.register_callbacks is None
    assert module.register_routes is None


def test_ada_ui_core_preserves_bootstrap_and_shared_tokens() -> None:
    resources = Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'ui' / 'core' / 'resources'
    bootstrap = (resources / 'css' / '00-bootstrap.min.css').read_text(encoding='utf-8')
    tokens = (resources / 'css' / '10-tokens.css').read_text(encoding='utf-8')
    css_list = (resources / 'css' / 'css.list').read_text(encoding='utf-8').splitlines()

    assert css_list == ['00-bootstrap.min.css', '10-tokens.css']
    assert 'Bootstrap  v5.3.3' in bootstrap
    assert '--primary-background: #EBEBEB;' in tokens
    assert '--loader-color: #2E2E2E;' in tokens
    assert '--dark-color: #313131;' in tokens


def test_ada_ui_core_does_not_bundle_unrelated_runtime_capabilities() -> None:
    resources = Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'ui' / 'core' / 'resources'

    assert not (resources / 'js').exists()
    assert not (resources / 'img').exists()
    assert not (resources / 'css' / '20-status.css').exists()
    assert not (resources / 'css' / '30-page-ready.css').exists()
