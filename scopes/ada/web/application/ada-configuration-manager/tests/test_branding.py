from __future__ import annotations

from importlib.resources import files

from ada.web.application.configuration_manager.branding import (
    ADA_MANAGER_BRAND_ASSETS,
    build_ada_manager_brand_marks,
    create_ada_manager_brand_module,
)
from atlanticus.web.manager.web.assets import manager_asset_layer


def test_ada_brands_belong_to_ada_composition_without_duplicating_generic_default():
    marks = build_ada_manager_brand_marks()
    assert [mark.role for mark in marks] == ['product', 'framework', 'organization']
    assert marks[0].logo_src.endswith('/img/ada-operational-secondary.svg')
    assert marks[1].logo_src.startswith(f'/assets/{manager_asset_layer().target_name}/img/')
    assert marks[2].logo_src.endswith('/img/amsa-pelambres-primary.png')
    assert create_ada_manager_brand_module().asset_layers == (ADA_MANAGER_BRAND_ASSETS,)


def test_brand_assets_are_packaged_in_owner_modules():
    application = files('ada.web.application.configuration_manager').joinpath('resources/img')
    framework = files('atlanticus.web.manager').joinpath('resources/img')
    assert application.joinpath('ada-operational-secondary.svg').read_bytes().startswith(b'<svg ')
    assert application.joinpath('amsa-pelambres-primary.png').read_bytes().startswith(bytes((137, 80, 78, 71)))
    assert framework.joinpath('atlanticus-primary.webp').read_bytes().startswith(b'RIFF')
