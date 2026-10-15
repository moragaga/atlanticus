import gzip
from pathlib import Path

from dash import html, page_container
from flask import Flask, request, send_from_directory

from atlanticus.web.application import create_web_application
from atlanticus.web.assets import AssetLayer, AssetPublication
from atlanticus.web.css_compression import register_css_compression
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition


def _css() -> bytes:
    return ('\n'.join(f'.tile-{index} {{ margin: {index}px; color: #123456; }}' for index in range(240)) + '\n').encode()


def _standalone(tmp_path: Path):
    root = tmp_path / 'assets'
    root.mkdir()
    body = _css()
    (root / 'app.min.css').write_bytes(body)
    (root / 'small.css').write_text('body{}', encoding='utf-8')
    (root / 'script.js').write_text('const a=1;', encoding='utf-8')
    (root / 'logo.webp').write_bytes(b'fake-webp-data')
    app = Flask(__name__)

    @app.get('/assets/<path:name>')
    def serve(name):
        return send_from_directory(root, name)

    @app.get('/health/live')
    def health():
        return {'status': 'alive'}

    register_css_compression(
        app,
        AssetPublication(
            assets_root=root,
            revision='test',
            manifest_path=root / 'manifest.json',
            css_entries=('app.min.css', 'small.css'),
            js_entries=('script.js',),
        ),
    )
    return app.test_client(), body


def test_large_css_is_gzipped_without_changing_identity(tmp_path):
    client, expected = _standalone(tmp_path)
    encoded = client.get('/assets/app.min.css', headers={'Accept-Encoding': 'gzip'})
    identity = client.get('/assets/app.min.css')

    assert encoded.status_code == 200
    assert encoded.headers['Content-Encoding'] == 'gzip'
    assert 'Accept-Encoding' in encoded.vary
    assert gzip.decompress(encoded.data) == expected
    assert len(encoded.data) < len(expected)
    assert identity.status_code == 200
    assert identity.data == expected
    assert 'Content-Encoding' not in identity.headers
    assert 'Accept-Encoding' in identity.vary
    assert identity.headers['ETag'] != encoded.headers['ETag']


def test_gzip_and_identity_etags_revalidate_independently(tmp_path):
    client, _ = _standalone(tmp_path)
    gzip_first = client.get('/assets/app.min.css', headers={'Accept-Encoding': 'gzip'})
    gzip_again = client.get(
        '/assets/app.min.css',
        headers={'Accept-Encoding': 'gzip', 'If-None-Match': gzip_first.headers['ETag']},
    )
    assert gzip_again.status_code == 304
    assert gzip_again.data == b''
    assert 'Accept-Encoding' in gzip_again.vary

    original = client.get('/assets/app.min.css')
    original_again = client.get(
        '/assets/app.min.css', headers={'If-None-Match': original.headers['ETag']}
    )
    assert original_again.status_code == 304
    assert original_again.data == b''
    assert 'Accept-Encoding' in original_again.vary


def test_gzip_disabled_and_ranges_keep_uncompressed_file_delivery(tmp_path):
    client, expected = _standalone(tmp_path)
    disallowed = client.get('/assets/app.min.css', headers={'Accept-Encoding': 'gzip;q=0'})
    partial = client.get(
        '/assets/app.min.css',
        headers={'Accept-Encoding': 'gzip', 'Range': 'bytes=0-9'},
    )
    assert disallowed.status_code == 200
    assert disallowed.data == expected
    assert 'Content-Encoding' not in disallowed.headers
    assert partial.status_code == 206
    assert partial.data == expected[:10]
    assert 'Content-Encoding' not in partial.headers
    assert 'Accept-Encoding' in partial.vary


def test_small_css_and_unrelated_resources_remain_uncompressed(tmp_path):
    client, _ = _standalone(tmp_path)
    for name in ('small.css', 'script.js', 'logo.webp'):
        response = client.get(f'/assets/{name}', headers={'Accept-Encoding': 'gzip'})
        assert response.status_code == 200
        assert 'Content-Encoding' not in response.headers
    assert 'Accept-Encoding' in client.get('/assets/small.css').vary
    assert 'Accept-Encoding' not in client.get('/assets/script.js').vary
    assert 'Accept-Encoding' not in client.get('/health/live').vary


def test_previous_request_guards_still_apply(tmp_path):
    root = tmp_path / 'assets'
    root.mkdir()
    (root / 'app.min.css').write_bytes(_css())
    app = Flask(__name__)

    @app.before_request
    def authorization():
        if request.args.get('deny') == '1':
            return 'Forbidden', 403

    @app.get('/assets/<path:name>')
    def serve(name):
        return send_from_directory(root, name)

    register_css_compression(
        app,
        AssetPublication(
            assets_root=root, revision='test', manifest_path=root / 'manifest.json',
            css_entries=('app.min.css',), js_entries=(),
        ),
    )
    denied = app.test_client().get('/assets/app.min.css?deny=1', headers={'Accept-Encoding': 'gzip'})
    assert denied.status_code == 403
    assert 'Content-Encoding' not in denied.headers


def test_integrated_dash_serves_optimized_bundle_with_gzip(tmp_path, monkeypatch):
    package = tmp_path / 'css_gzip_pages'
    package.mkdir()
    (package / '__init__.py').write_text('', encoding='utf-8')
    (package / 'home.py').write_text(
        "from dash import html, register_page\nregister_page(__name__, path='/')\nlayout = html.Div('Home')\n",
        encoding='utf-8',
    )
    source = tmp_path / 'layer' / 'resources' / 'css'
    source.mkdir(parents=True)
    (source / 'main.css').write_bytes(_css())
    (source / 'css.list').write_text('main.css\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.delenv('ATLANTICUS_WEB_ASSETS_OPTIMIZED', raising=False)

    runtime = create_web_application(
        WebApplicationDefinition(
            import_name='css_gzip_test_web',
            metadata=ApplicationMetadata(
                application_id='css-gzip-test', display_name='CSS Gzip', version='1.0.0'
            ),
            publications_root=tmp_path / 'published',
            layout=lambda _services: html.Main(page_container),
            page_packages=('css_gzip_pages',),
            asset_layers=(
                AssetLayer(name='test', load_order=100, source_directory=tmp_path / 'layer'),
            ),
        ),
        assets_optimized=True,
    )
    assert runtime.assets.css_entries == ('app.min.css',)
    client = runtime.server.test_client()
    raw = client.get('/assets/app.min.css')
    encoded = client.get('/assets/app.min.css', headers={'Accept-Encoding': 'gzip'})
    assert raw.status_code == 200
    assert encoded.status_code == 200
    assert gzip.decompress(encoded.data) == raw.data
    assert encoded.headers['Content-Encoding'] == 'gzip'
