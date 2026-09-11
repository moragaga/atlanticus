from __future__ import annotations

import posixpath
import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from rcssmin import cssmin
from rjsmin import jsmin

from atlanticus.web.errors import WebAssetError

_CSS_BUNDLE_NAME = 'app.min.css'
_CSS_URL_PATTERN = re.compile(
    r'url\(\s*(?P<quote>[\'\"]?)(?P<value>.*?)(?P=quote)\s*\)',
    re.IGNORECASE,
)


def optimize_staged_assets(staging: Path, manifest: dict[str, Any]) -> None:
    css_entries = tuple(manifest.get('css_entries', ()))
    js_entries = tuple(manifest.get('js_entries', ()))

    if css_entries:
        source = '\n'.join(_read_css_for_bundle(staging, relative) for relative in css_entries)
        bundle = staging / _CSS_BUNDLE_NAME
        bundle.write_text(cssmin(source).rstrip() + '\n', encoding='utf-8')
        for relative in css_entries:
            (staging / relative).unlink()
        for list_path in staging.rglob('css/css.list'):
            list_path.unlink()
        manifest['css_entries'] = [_CSS_BUNDLE_NAME]

    for relative in js_entries:
        path = staging / relative
        path.write_text(
            jsmin(path.read_text(encoding='utf-8')).rstrip() + '\n',
            encoding='utf-8',
        )


def _read_css_for_bundle(staging: Path, relative: str) -> str:
    content = (staging / relative).read_text(encoding='utf-8')
    return _rebase_css_urls(content, source_parent=PurePosixPath(relative).parent)


def _rebase_css_urls(content: str, *, source_parent: PurePosixPath) -> str:
    def replace(match: re.Match[str]) -> str:
        quote = match.group('quote')
        value = match.group('value').strip()
        rebased = _rebase_css_url(value, source_parent=source_parent)
        return f'url({quote}{rebased}{quote})'

    return _CSS_URL_PATTERN.sub(replace, content)


def _rebase_css_url(value: str, *, source_parent: PurePosixPath) -> str:
    if not value or value.startswith(('#', '/')):
        return value

    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return value

    target = posixpath.normpath(posixpath.join(source_parent.as_posix(), parsed.path))
    if target == '..' or target.startswith('../') or target.startswith('/'):
        raise WebAssetError(f'CSS asset URL escapes the publication root: {value}')

    result = target
    if parsed.query:
        result += f'?{parsed.query}'
    if parsed.fragment:
        result += f'#{parsed.fragment}'
    return result
