from __future__ import annotations

import gzip
import hashlib
import mimetypes
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from flask import Flask, Response, request

from atlanticus.web.assets import AssetPublication

_STATIC_SUFFIXES = {'.css', '.js', '.svg'}
_DASH_BOOTSTRAP_PATHS = {'/_dash-layout', '/_dash-dependencies'}
_DASH_JSON_PATHS = {'/_dash-layout', '/_dash-dependencies', '/_dash-update-component'}
_DASH_SUITE_PREFIX = '/_dash-component-suites/'
_MINIMUM_ASSET_BYTES = 256
_MINIMUM_DASH_BYTES = 1024
_CACHE_BUDGET_BYTES = 8 * 1024 * 1024
_MAXIMUM_RESPONSE_BYTES = 8 * 1024 * 1024


class _EncodedResponseCache:
    def __init__(self) -> None:
        self._entries: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self._size = 0
        self._lock = RLock()

    def compress(self, path: str, identity: bytes) -> bytes:
        key = (path, hashlib.sha256(identity).hexdigest())
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached
        encoded = gzip.compress(identity, compresslevel=6, mtime=0)
        if len(encoded) >= len(identity) or len(encoded) > _CACHE_BUDGET_BYTES:
            return encoded
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached
            self._entries[key] = encoded
            self._size += len(encoded)
            while self._size > _CACHE_BUDGET_BYTES:
                _, expired = self._entries.popitem(last=False)
                self._size -= len(expired)
        return encoded


def register_http_compression(server: Flask, publication: AssetPublication) -> None:
    compressed: dict[str, tuple[bytes, str, datetime, str]] = {}
    candidate_paths: set[str] = set()
    root = Path(publication.assets_root)
    candidates = set(publication.css_entries) | set(publication.js_entries)
    candidates.update(path.relative_to(root).as_posix() for path in root.rglob('*.svg') if path.is_file())

    for entry in sorted(candidates):
        file_path = root / entry
        if file_path.suffix.lower() not in _STATIC_SUFFIXES or not file_path.is_file():
            continue
        url = f'/assets/{entry}'
        candidate_paths.add(url)
        identity = file_path.read_bytes()
        if len(identity) < _MINIMUM_ASSET_BYTES:
            continue
        encoded = gzip.compress(identity, compresslevel=6, mtime=0)
        if len(encoded) >= len(identity):
            continue
        compressed[url] = (
            encoded,
            hashlib.sha256(encoded).hexdigest(),
            datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC),
            mimetypes.guess_type(entry)[0] or 'application/octet-stream',
        )

    suites = _EncodedResponseCache()

    @server.before_request
    def serve_encoded_asset() -> Response | None:
        if request.method not in {'GET', 'HEAD'} or request.headers.get('Range'):
            return None
        if not _accepts_gzip():
            return None
        cached = compressed.get(request.path)
        if cached is None:
            return None
        encoded, etag, modified, content_type = cached
        response = Response(encoded, mimetype=content_type)
        response.headers['Content-Encoding'] = 'gzip'
        response.cache_control.no_cache = True
        response.last_modified = modified
        response.set_etag(etag)
        return response.make_conditional(request)

    @server.after_request
    def compress_http_response(response: Response) -> Response:
        if request.path in candidate_paths:
            response.vary.add('Accept-Encoding')
            return response

        suite = request.path.startswith(_DASH_SUITE_PREFIX)
        dash_json = request.path in _DASH_JSON_PATHS
        if not suite and not dash_json:
            return response
        if suite and response.mimetype not in {'text/javascript', 'application/javascript', 'application/x-javascript'}:
            return response
        if dash_json and response.mimetype != 'application/json':
            return response
        if response.status_code not in {200, 304}:
            return response
        response.vary.add('Accept-Encoding')
        if request.path in _DASH_BOOTSTRAP_PATHS:
            response.headers['Cache-Control'] = 'no-store'
            response.headers.pop('ETag', None)
            response.headers.pop('Last-Modified', None)
        if response.status_code != 200 or not _accepts_gzip():
            return response
        if request.method not in {'GET', 'HEAD', 'POST'} or request.headers.get('Range'):
            return response
        if response.headers.get('Content-Encoding') or response.cache_control.no_transform:
            return response
        if response.headers.get('Content-Length'):
            try:
                length = int(response.headers['Content-Length'])
            except ValueError:
                return response
            if length < _MINIMUM_DASH_BYTES or length > _MAXIMUM_RESPONSE_BYTES:
                return response
        if response.is_streamed and not response.direct_passthrough:
            return response

        response.direct_passthrough = False
        identity = response.get_data()
        if not _MINIMUM_DASH_BYTES <= len(identity) <= _MAXIMUM_RESPONSE_BYTES:
            return response
        encoded = suites.compress(request.path, identity) if suite else gzip.compress(
            identity, compresslevel=6, mtime=0
        )
        if len(encoded) >= len(identity):
            return response

        etag = response.get_etag()
        response.set_data(encoded)
        response.headers['Content-Encoding'] = 'gzip'
        if etag[0] is not None:
            response.set_etag(f'gzip-{etag[0]}', weak=etag[1])
            if request.method in {'GET', 'HEAD'}:
                return response.make_conditional(request)
        return response


def _accepts_gzip() -> bool:
    return (request.accept_encodings.quality('gzip') or 0) > 0
