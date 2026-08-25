from __future__ import annotations

from pathlib import Path
from typing import Any

from rcssmin import cssmin
from rjsmin import jsmin

_CSS_BUNDLE_NAME = 'app.min.css'


def optimize_staged_assets(staging: Path, manifest: dict[str, Any]) -> None:
    css_entries = tuple(manifest.get('css_entries', ()))
    js_entries = tuple(manifest.get('js_entries', ()))

    if css_entries:
        source = '\n'.join(
            (staging / relative).read_text(encoding='utf-8') for relative in css_entries
        )
        bundle = staging / _CSS_BUNDLE_NAME
        bundle.write_text(cssmin(source).rstrip() + '\n', encoding='utf-8')
        for relative in css_entries:
            (staging / relative).unlink()
        for list_path in staging.rglob('css/css.list'):
            list_path.unlink()
        manifest['css_entries'] = [_CSS_BUNDLE_NAME]

    for relative in js_entries:
        path = staging / relative
        path.write_text(jsmin(path.read_text(encoding='utf-8')).rstrip() + '\n', encoding='utf-8')
