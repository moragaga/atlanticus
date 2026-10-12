import hashlib
import struct
import zlib
from dataclasses import replace
from pathlib import Path

import pytest

from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.descriptor import GENERIC_APPLICATION_DESCRIPTOR
from atlanticus.web.application import create_web_application
from atlanticus.web.assets import AssetLayer
from atlanticus.web.errors import WebDefinitionError


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack('>I', len(data))
        + kind
        + data
        + struct.pack('>I', zlib.crc32(kind + data))
    )


def _png(width: int = 32, height: int = 32, rgb: bytes = b'\x00\x80\xff') -> bytes:
    scanlines = (b'\x00' + rgb * width) * height
    return (
        b'\x89PNG\r\n\x1a\n'
        + _png_chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b'IDAT', zlib.compress(scanlines))
        + _png_chunk(b'IEND', b'')
    )


def _descriptor_with_favicon(tmp_path, monkeypatch, *, icon: bytes | None, name='favicon.png'):
    package_name = 'favicon_fixture_' + hashlib.sha256(str(tmp_path).encode()).hexdigest()[:12]
    package = tmp_path / package_name
    resource = package / 'resources' / 'img'
    resource.mkdir(parents=True)
    (package / '__init__.py').write_text('', encoding='utf-8')
    if icon is not None:
        (resource / name).write_bytes(icon)
    monkeypatch.syspath_prepend(str(tmp_path))
    layer = AssetLayer(
        name='app_favicon_fixture',
        load_order=206,
        package=package_name,
    )
    return replace(
        GENERIC_APPLICATION_DESCRIPTOR,
        application_root=tmp_path,
        favicon_asset_layer=layer,
    )


def test_generic_application_without_custom_favicon_retains_pwa_fallback(tmp_path):
    descriptor = replace(GENERIC_APPLICATION_DESCRIPTOR, application_root=tmp_path)
    definition = create_application_definition(application_descriptor=descriptor)
    module = next(module for module in definition.modules if module.name == 'pwa')

    assert len(definition.asset_layers) == 1
    assert module.index.head_fragments[-1] == (
        '<link rel="icon" type="image/png" '
        'href="/assets/0205_ada_application_pwa/img/ada-pwa-icon-192.png">'
    )


def test_packaged_favicon_is_served_and_does_not_change_pwa_manifest(tmp_path, monkeypatch):
    png = _png()
    descriptor = _descriptor_with_favicon(tmp_path, monkeypatch, icon=png)
    definition = create_application_definition(application_descriptor=descriptor)
    module = next(module for module in definition.modules if module.name == 'pwa')
    expected = (
        '/assets/0206_app_favicon_fixture/img/favicon.png?v='
        + hashlib.sha256(png).hexdigest()[:12]
    )

    favicon_links = [fragment for fragment in module.index.head_fragments if 'rel="icon"' in fragment]
    assert favicon_links == [f'<link rel="icon" type="image/png" href="{expected}">']
    assert len(definition.asset_layers) == 2

    runtime = create_web_application(definition)
    client = runtime.server.test_client()
    response = client.get(expected)
    assert response.status_code == 200
    assert response.data == png
    assert response.mimetype == 'image/png'

    manifest = client.get('/manifest.webmanifest').get_json()
    assert len(manifest['icons']) == 3
    assert all('favicon.png' not in icon['src'] for icon in manifest['icons'])


@pytest.mark.parametrize('icon', [None, b'not a png', _png(width=31)])
def test_declared_missing_or_invalid_favicon_fails_before_startup(tmp_path, monkeypatch, icon):
    descriptor = _descriptor_with_favicon(tmp_path, monkeypatch, icon=icon)
    with pytest.raises(WebDefinitionError, match='Application favicon'):
        create_application_definition(application_descriptor=descriptor)


def test_favicon_descriptor_does_not_accept_local_source_directory(tmp_path):
    with pytest.raises(ValueError, match='packaged AssetLayer'):
        replace(
            GENERIC_APPLICATION_DESCRIPTOR,
            favicon_asset_layer=AssetLayer(
                name='local_favicon',
                load_order=206,
                source_directory=tmp_path,
            ),
        )


def _ico(width: int = 64, height: int = 64) -> bytes:
    png = _png(width=width, height=height)
    entry = struct.pack('<BBBBHHII', width, height, 0, 0, 1, 32, len(png), 22)
    return struct.pack('<HHH', 0, 1, 1) + entry + png


def test_packaged_64x64_ico_is_served_and_keeps_pwa_manifest(tmp_path, monkeypatch):
    content = _ico()
    descriptor = _descriptor_with_favicon(
        tmp_path, monkeypatch, icon=content, name='favicon.ico'
    )
    definition = create_application_definition(application_descriptor=descriptor)
    module = next(module for module in definition.modules if module.name == 'pwa')
    src = '/assets/0206_app_favicon_fixture/img/favicon.ico?v=' + hashlib.sha256(content).hexdigest()[:12]
    favicon_links = [fragment for fragment in module.index.head_fragments if 'rel="icon"' in fragment]
    assert favicon_links == [f'<link rel="icon" type="image/x-icon" href="{src}">']

    runtime = create_web_application(definition)
    client = runtime.server.test_client()
    response = client.get(src)
    assert response.status_code == 200
    assert response.data == content
    assert response.mimetype in ('image/x-icon', 'image/vnd.microsoft.icon')
    manifest = client.get('/manifest.webmanifest').get_json()
    assert len(manifest['icons']) == 3
    assert all('favicon.ico' not in icon['src'] for icon in manifest['icons'])


@pytest.mark.parametrize('icon', [b'bad', _ico(width=32, height=32), _ico()[:23]])
def test_invalid_ico_is_rejected_before_startup(tmp_path, monkeypatch, icon):
    descriptor = _descriptor_with_favicon(
        tmp_path, monkeypatch, icon=icon, name='favicon.ico'
    )
    with pytest.raises(WebDefinitionError, match='Application favicon ICO'):
        create_application_definition(application_descriptor=descriptor)


def test_both_icon_formats_are_rejected(tmp_path, monkeypatch):
    descriptor = _descriptor_with_favicon(tmp_path, monkeypatch, icon=_png())
    import importlib

    package = importlib.import_module(descriptor.favicon_asset_layer.package)
    (Path(package.__file__).parent / 'resources/img/favicon.ico').write_bytes(_ico())
    with pytest.raises(WebDefinitionError, match='exactly one'):
        create_application_definition(application_descriptor=descriptor)
