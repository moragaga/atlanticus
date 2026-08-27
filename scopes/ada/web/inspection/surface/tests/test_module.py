import pytest

from ada.web.inspection.surface import (
    ADA_KPI_INSPECTION_SURFACE_ASSET_LAYER,
    create_kpi_inspection_surface_module,
)


def test_surface_module_contributes_stable_index_fragment_and_assets() -> None:
    module = create_kpi_inspection_surface_module()

    assert module.name == 'kpi-inspection-surface'
    assert module.asset_layers == (ADA_KPI_INSPECTION_SURFACE_ASSET_LAYER,)
    assert ADA_KPI_INSPECTION_SURFACE_ASSET_LAYER.load_order == 300
    assert module.index.runtime_config == {'api_base_path': '/api/inspection/kpis'}
    assert len(module.index.body_end_fragments) == 1
    assert 'id="ada-kpi-inspection-surface"' in module.index.body_end_fragments[0]


def test_surface_api_path_is_normalized_without_binding_to_flask() -> None:
    module = create_kpi_inspection_surface_module(api_base_path=' /custom/inspection/ ')

    assert module.index.runtime_config == {'api_base_path': '/custom/inspection'}


@pytest.mark.parametrize('value', ['', '   ', '/', 'relative/path'])
def test_surface_rejects_non_absolute_api_path(value: str) -> None:
    with pytest.raises(ValueError, match='API base path must be an absolute non-root path'):
        create_kpi_inspection_surface_module(api_base_path=value)


def test_surface_fragment_is_rendered_outside_dash_app_entry() -> None:
    from atlanticus.web.index import IndexPageDefinition, render_index_string

    module = create_kpi_inspection_surface_module()
    index = render_index_string(
        application_id='test-app',
        display_name='Test App',
        version='0.1.0',
        definition=IndexPageDefinition(),
        module_contributions=((module.name, module.index),),
    )

    assert index.index('{%app_entry%}') < index.index('id="ada-kpi-inspection-surface"')
    assert index.index('id="ada-kpi-inspection-surface"') < index.index('atlanticus-runtime-config')
