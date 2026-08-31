from __future__ import annotations

import json
import re
from importlib.resources import files

from flask import Flask, Response

from atlanticus.web.pwa.models import WebPwaDefinition

_CACHE_SEGMENT_PATTERN = re.compile(r'[^a-zA-Z0-9._-]+')


def register_pwa_routes(app: Flask, definition: WebPwaDefinition) -> None:
    @app.get('/manifest.webmanifest')
    def atlanticus_pwa_manifest() -> Response:
        content = json.dumps(
            definition.to_manifest(),
            ensure_ascii=False,
            separators=(',', ':'),
        )
        response = Response(content, mimetype='application/manifest+json')
        _set_no_cache_headers(response)
        return response

    @app.get('/service-worker.js')
    def atlanticus_pwa_service_worker() -> Response:
        template = (
            files('atlanticus.web.pwa')
            .joinpath('resources', 'service-worker.js')
            .read_text(encoding='utf-8')
        )
        content = template.replace('__CACHE_NAME__', _cache_name(definition))
        response = Response(content, mimetype='application/javascript')
        response.headers['Service-Worker-Allowed'] = definition.scope
        _set_no_cache_headers(response)
        return response


def _cache_name(definition: WebPwaDefinition) -> str:
    application_id = _safe_cache_segment(definition.application_id)
    version = _safe_cache_segment(definition.version)
    return f'atlanticus-pwa:{application_id}:{version}'


def _safe_cache_segment(value: str) -> str:
    return _CACHE_SEGMENT_PATTERN.sub('_', value.strip())[:80] or 'unknown'


def _set_no_cache_headers(response: Response) -> None:
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
