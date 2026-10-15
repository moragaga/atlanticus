from __future__ import annotations

import gzip
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, Response, request

from atlanticus.web.assets import AssetPublication

def register_css_compression(server: Flask, publication: AssetPublication) -> None:
    compressed: dict[str, tuple[bytes, str, datetime]] = {}
    css_paths: set[str] = set()

    for entry in publication.css_entries:
        path = Path(publication.assets_root) / entry
        url = f'/assets/{entry}'
        css_paths.add(url)
        body = path.read_bytes()
        encoded = gzip.compress(body, compresslevel=6, mtime=0)
        if len(encoded) >= len(body):
            continue
        compressed[url] = (
            encoded,
            hashlib.sha256(encoded).hexdigest(),
            datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
        )

    @server.before_request
    def serve_compressed_css() -> Response | None:
        if request.method not in {'GET', 'HEAD'} or request.headers.get('Range'):
            return None
        if not (request.accept_encodings.quality('gzip') or 0) > 0:
            return None
        cached = compressed.get(request.path)
        if cached is None:
            return None
        encoded, etag, modified = cached
        response = Response(encoded, mimetype='text/css')
        response.headers['Content-Encoding'] = 'gzip'
        response.cache_control.no_cache = True
        response.last_modified = modified
        response.set_etag(etag)
        return response.make_conditional(request)

    @server.after_request
    def vary_css_by_encoding(response: Response) -> Response:
        if request.path in css_paths and response.mimetype == 'text/css':
            response.vary.add('Accept-Encoding')
        return response
