import gzip
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from atlanticus.web.assets import AssetPublication
from atlanticus.web.http_compression import register_http_compression


def _client(tmp_path: Path):
    root = tmp_path / 'published'
    root.mkdir()
    javascript = ('function renderCard(x) { return x + 42; }\n' * 400).encode()
    svg = ('<svg xmlns="http://www.w3.org/2000/svg">' + '<rect width="10" height="10"/>' * 100 + '</svg>').encode()
    (root / 'script.js').write_bytes(javascript)
    (root / 'diagram.svg').write_bytes(svg)
    (root / 'image.webp').write_bytes(b'webp-original-bytes')
    app = Flask(__name__)

    @app.get('/assets/<path:filename>')
    def asset(filename):
        return send_from_directory(root, filename)

    @app.get('/_dash-component-suites/test/chunk.js')
    def suite():
        return send_from_directory(root, 'script.js', max_age=31536000)

    @app.get('/_dash-layout')
    def layout():
        return jsonify({'layout': ['item'] * 1000})

    @app.get('/_dash-dependencies')
    def dependencies():
        return jsonify({'dependencies': [{'output': str(n)} for n in range(400)]})

    @app.post('/_dash-update-component')
    def callback():
        return jsonify({'response': {'values': list(range(800))}})

    @app.get('/_dash-update-small')
    def unrelated():
        return jsonify({'response': 'untouched'})

    @app.get('/health/live')
    def health():
        return jsonify({'status': 'alive'})

    register_http_compression(app, AssetPublication(
        assets_root=root, revision='test', manifest_path=root / 'manifest.json',
        css_entries=(), js_entries=('script.js',),
    ))
    return app.test_client(), javascript, svg


def test_publication_javascript_and_svg_use_cached_gzip(tmp_path):
    client, javascript, svg = _client(tmp_path)
    for name, expected in [('script.js', javascript), ('diagram.svg', svg)]:
        url = f'/assets/{name}'
        encoded = client.get(url, headers={'Accept-Encoding': 'gzip'})
        identity = client.get(url)
        assert encoded.status_code == 200
        assert encoded.headers['Content-Encoding'] == 'gzip'
        assert gzip.decompress(encoded.data) == expected
        assert len(encoded.data) < len(identity.data)
        assert identity.data == expected
        assert 'Content-Encoding' not in identity.headers
        assert 'Accept-Encoding' in identity.vary
        assert identity.headers['ETag'] != encoded.headers['ETag']
        cached = client.get(url, headers={
            'Accept-Encoding': 'gzip', 'If-None-Match': encoded.headers['ETag'],
        })
        assert cached.status_code == 304
        assert 'Accept-Encoding' in cached.vary


def test_dash_javascript_preserves_conditional_etag_and_uses_gzip(tmp_path):
    client, javascript, _ = _client(tmp_path)
    url = '/_dash-component-suites/test/chunk.js'
    encoded = client.get(url, headers={'Accept-Encoding': 'gzip'})
    identity = client.get(url)
    assert encoded.status_code == 200
    assert encoded.headers['Content-Encoding'] == 'gzip'
    assert gzip.decompress(encoded.data) == javascript
    assert 'Accept-Encoding' in identity.vary
    assert identity.data == javascript
    assert encoded.headers['ETag'] != identity.headers['ETag']
    assert encoded.headers['Cache-Control'] == identity.headers['Cache-Control']
    cached = client.get(url, headers={
        'Accept-Encoding': 'gzip', 'If-None-Match': encoded.headers['ETag'],
    })
    assert cached.status_code == 304
    assert 'Accept-Encoding' in cached.vary


def test_dash_json_endpoints_compress_without_modifying_payload(tmp_path):
    client, _, _ = _client(tmp_path)
    for method, path in [('get', '/_dash-layout'), ('get', '/_dash-dependencies'), ('post', '/_dash-update-component')]:
        plain = getattr(client, method)(path)
        compressed = getattr(client, method)(path, headers={'Accept-Encoding': 'gzip'})
        assert plain.status_code == compressed.status_code == 200
        assert plain.mimetype == compressed.mimetype == 'application/json'
        assert gzip.decompress(compressed.data) == plain.data
        assert compressed.headers['Content-Encoding'] == 'gzip'
        assert 'Accept-Encoding' in plain.vary
        assert len(compressed.data) < len(plain.data)


def test_declined_encoding_partial_content_and_other_resources_remain_identity(tmp_path):
    client, javascript, _ = _client(tmp_path)
    denied = client.get('/assets/script.js', headers={'Accept-Encoding': 'gzip;q=0'})
    ranged = client.get('/assets/script.js', headers={
        'Accept-Encoding': 'gzip', 'Range': 'bytes=0-19',
    })
    picture = client.get('/assets/image.webp', headers={'Accept-Encoding': 'gzip'})
    health = client.get('/health/live', headers={'Accept-Encoding': 'gzip'})
    assert denied.data == javascript
    assert 'Content-Encoding' not in denied.headers
    assert ranged.status_code == 206
    assert ranged.data == javascript[:20]
    assert 'Content-Encoding' not in ranged.headers
    assert 'Accept-Encoding' in ranged.vary
    assert 'Content-Encoding' not in picture.headers
    assert 'Accept-Encoding' not in picture.vary
    assert 'Content-Encoding' not in health.headers
    assert 'Accept-Encoding' not in health.vary


def test_dash_suite_range_is_not_recompressed(tmp_path):
    client, javascript, _ = _client(tmp_path)
    response = client.get('/_dash-component-suites/test/chunk.js', headers={
        'Accept-Encoding': 'gzip', 'Range': 'bytes=0-9',
    })
    assert response.status_code == 206
    assert response.data == javascript[:10]
    assert 'Content-Encoding' not in response.headers
    assert 'Accept-Encoding' not in response.vary
