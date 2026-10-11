from __future__ import annotations

import posixpath
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import pytest

from atlanticus.web.assets import publish_asset_layers
from atlanticus.web.bootstrap import BOOTSTRAP_FOUNDATION_ASSET_LAYER

_CSS_URL = re.compile(r'url\(\s*([\"\']?)(.*?)\1\s*\)', re.IGNORECASE)
_SOURCE_MAP = re.compile(r'/\*[#@]\s*sourceMappingURL=')


@pytest.mark.parametrize('optimize', [False, True], ids=['development', 'production'])
def test_bootstrap_foundation_publishes_self_contained_assets(tmp_path, optimize: bool) -> None:
    publication = publish_asset_layers(
        layers=(BOOTSTRAP_FOUNDATION_ASSET_LAYER,),
        publications_root=tmp_path / 'publications',
        optimize=optimize,
    )

    assert len(publication.css_entries) == (1 if optimize else 2)
    assert publication.js_entries == ()

    published = publication.assets_root
    font_root = published / BOOTSTRAP_FOUNDATION_ASSET_LAYER.target_name / 'fonts'
    assert (font_root / 'bootstrap-icons.woff').is_file()
    assert (font_root / 'bootstrap-icons.woff2').is_file()

    css_contents = []
    for css_entry in publication.css_entries:
        content = (published / css_entry).read_text(encoding='utf-8')
        css_contents.append(content)
        assert _SOURCE_MAP.search(content) is None

        css_directory = PurePosixPath(css_entry).parent
        for match in _CSS_URL.finditer(content):
            raw_url = match.group(2).strip()
            if not raw_url or raw_url.startswith(('#', 'data:')):
                continue
            parsed = urlsplit(raw_url)
            assert not parsed.scheme and not parsed.netloc, raw_url
            assert parsed.path and not parsed.path.startswith('/'), raw_url
            target = posixpath.normpath(posixpath.join(css_directory.as_posix(), parsed.path))
            assert not target.startswith('../'), raw_url
            assert (published / target).is_file(), raw_url

    assert any('bootstrap-icons.woff2' in content for content in css_contents)
