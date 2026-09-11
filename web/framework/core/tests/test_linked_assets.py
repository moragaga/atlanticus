from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atlanticus.web.assets import AssetLayer, publish_asset_layers
from atlanticus.web.errors import WebAssetError

_ROOT = Path(__file__).resolve().parents[1]


def _linked_layer(tmp_path: Path, css: str) -> AssetLayer:
    root = tmp_path / 'linked' / 'resources'
    (root / 'css').mkdir(parents=True)
    (root / 'fonts').mkdir(parents=True)
    (root / 'css' / '10-linked.css').write_text(css, encoding='utf-8')
    (root / 'css' / 'css.list').write_text('10-linked.css\n', encoding='utf-8')
    (root / 'fonts' / 'linked.woff2').write_bytes(b'linked-font')
    return AssetLayer(name='linked', load_order=100, source_directory=tmp_path / 'linked')


def test_asset_publication_copies_font_resources(tmp_path: Path) -> None:
    layer = _linked_layer(tmp_path, '.linked { font-family: linked; }')

    publication = publish_asset_layers(layers=(layer,), publications_root=tmp_path / 'published')

    font = publication.assets_root / '0100_linked/fonts/linked.woff2'
    assert font.read_bytes() == b'linked-font'


def test_optimized_css_rebases_relative_asset_urls_to_bundle_root(tmp_path: Path) -> None:
    layer = _linked_layer(
        tmp_path,
        '@font-face { src: url("../fonts/linked.woff2?rev=1#font"); }',
    )

    publication = publish_asset_layers(
        layers=(layer,),
        publications_root=tmp_path / 'published',
        optimize=True,
    )

    css = (publication.assets_root / 'app.min.css').read_text(encoding='utf-8')
    assert '0100_linked/fonts/linked.woff2?rev=1#font' in css
    assert (publication.assets_root / '0100_linked/fonts/linked.woff2').is_file()


def test_optimized_css_preserves_non_relative_urls(tmp_path: Path) -> None:
    layer = _linked_layer(
        tmp_path,
        '.a{src:url("https://example.test/a.woff2")}'
        '.b{src:url("/assets/a.woff2")}'
        '.c{src:url("data:font/woff2;base64,AAAA")}'
        '.d{src:url("#glyph")}',
    )

    publication = publish_asset_layers(
        layers=(layer,),
        publications_root=tmp_path / 'published',
        optimize=True,
    )

    css = (publication.assets_root / 'app.min.css').read_text(encoding='utf-8')
    assert 'https://example.test/a.woff2' in css
    assert '/assets/a.woff2' in css
    assert 'data:font/woff2;base64,AAAA' in css
    assert '#glyph' in css


def test_optimized_css_rejects_asset_url_escaping_publication_root(tmp_path: Path) -> None:
    layer = _linked_layer(tmp_path, '.bad { src: url("../../../outside.woff2"); }')

    with pytest.raises(WebAssetError, match='escapes the publication root'):
        publish_asset_layers(
            layers=(layer,),
            publications_root=tmp_path / 'published',
            optimize=True,
        )


def test_asset_sources_and_commented_mirrors_are_ast_equivalent() -> None:
    for filename in ('assets.py', 'asset_optimization.py'):
        productive = _ROOT / 'src' / 'atlanticus' / 'web' / filename
        commented = _ROOT / 'commented' / 'atlanticus' / 'web' / filename
        assert ast.dump(ast.parse(productive.read_text(encoding='utf-8'))) == ast.dump(
            ast.parse(commented.read_text(encoding='utf-8'))
        )
