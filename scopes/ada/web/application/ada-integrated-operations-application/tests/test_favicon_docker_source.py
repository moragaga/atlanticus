from pathlib import Path

from ada.web.application.integrated_operations.descriptor import (
    INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR,
    _resolve_favicon_asset_layer,
)


def test_specialized_descriptor_retains_default_without_uploaded_icon():
    declared = INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR.favicon_asset_layer
    location = (
        Path(__file__).resolve().parents[1]
        / 'src/ada/web/application/integrated_operations/resources/favicon/img/favicon.ico'
    )
    assert (declared is not None) == location.is_file()


def test_docker_source_favicon_is_detected_without_wheel(tmp_path):
    assert _resolve_favicon_asset_layer(tmp_path) is None
    resource = tmp_path / 'resources/favicon/img/favicon.ico'
    resource.parent.mkdir(parents=True)
    resource.write_bytes(b'icon available in the mounted application source')
    layer = _resolve_favicon_asset_layer(tmp_path)
    assert layer is not None
    assert layer.name == 'ada_integrated_operations_favicon'
    assert layer.load_order == 206
    assert layer.package == 'ada.web.application.integrated_operations'
    assert layer.resource_directory == 'resources/favicon'
