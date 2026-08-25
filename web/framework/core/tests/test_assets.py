from pathlib import Path

import pytest

from atlanticus.web.assets import AssetLayer, publish_asset_layers
from atlanticus.web.errors import WebAssetError, WebDefinitionError


def _layer(tmp_path: Path, name: str, order: int, css: tuple[str, ...], js: tuple[str, ...]):
    root = tmp_path / name / 'resources'
    (root / 'css').mkdir(parents=True)
    (root / 'js').mkdir(parents=True)
    for filename in css:
        (root / 'css' / filename).write_text(filename, encoding='utf-8')
    for filename in js:
        (root / 'js' / filename).write_text(filename, encoding='utf-8')
    (root / 'css' / 'css.list').write_text('\n'.join(css) + '\n', encoding='utf-8')
    (root / 'js' / 'js.list').write_text('\n'.join(js) + '\n', encoding='utf-8')
    return AssetLayer(name=name, load_order=order, source_directory=tmp_path / name)


def test_asset_publication_encodes_layer_and_list_order(tmp_path):
    later = _layer(tmp_path, 'later', 900, ('z.css', 'a.css'), ('z.js', 'a.js'))
    earlier = _layer(tmp_path, 'earlier', 100, ('b.css', 'a.css'), ('b.js', 'a.js'))

    publication = publish_asset_layers(
        layers=(later, earlier),
        publications_root=tmp_path / 'published',
    )

    assert publication.css_entries == (
        '0100_earlier/css/0000__b.css',
        '0100_earlier/css/0001__a.css',
        '0900_later/css/0000__z.css',
        '0900_later/css/0001__a.css',
    )
    assert publication.js_entries == (
        '0100_earlier/js/0000__b.js',
        '0100_earlier/js/0001__a.js',
        '0900_later/js/0000__z.js',
        '0900_later/js/0001__a.js',
    )


def test_asset_publication_is_revision_stable(tmp_path):
    layer = _layer(tmp_path, 'base', 100, ('a.css',), ('a.js',))
    first = publish_asset_layers(layers=(layer,), publications_root=tmp_path / 'published')
    second = publish_asset_layers(layers=(layer,), publications_root=tmp_path / 'published')

    assert first.revision == second.revision
    assert first.assets_root == second.assets_root


def test_asset_layer_rejects_duplicate_load_order(tmp_path):
    one = _layer(tmp_path, 'one', 100, ('a.css',), ('a.js',))
    two = _layer(tmp_path, 'two', 100, ('b.css',), ('b.js',))

    with pytest.raises(WebDefinitionError, match='load order is duplicated'):
        publish_asset_layers(layers=(one, two), publications_root=tmp_path / 'published')


def test_asset_list_must_be_exhaustive(tmp_path):
    root = tmp_path / 'bad' / 'resources'
    (root / 'css').mkdir(parents=True)
    (root / 'js').mkdir(parents=True)
    (root / 'css' / 'a.css').write_text('a', encoding='utf-8')
    (root / 'css' / 'b.css').write_text('b', encoding='utf-8')
    (root / 'css' / 'css.list').write_text('a.css\n', encoding='utf-8')
    layer = AssetLayer(name='bad', load_order=100, source_directory=tmp_path / 'bad')

    with pytest.raises(WebAssetError, match='declare every packaged css file exactly once'):
        publish_asset_layers(layers=(layer,), publications_root=tmp_path / 'published')


def test_asset_publication_tolerates_equivalent_concurrent_publish(tmp_path, monkeypatch):
    import shutil

    import atlanticus.web.assets as assets_module

    layer = _layer(tmp_path, 'base', 100, ('a.css',), ('a.js',))
    original_replace = assets_module.os.replace
    raced = False

    def replace_with_race(source, target):
        nonlocal raced
        if raced:
            return original_replace(source, target)
        raced = True
        shutil.copytree(source, target)
        raise FileExistsError

    monkeypatch.setattr(assets_module.os, 'replace', replace_with_race)

    publication = publish_asset_layers(
        layers=(layer,),
        publications_root=tmp_path / 'published',
    )

    assert publication.assets_root.is_dir()
    assert publication.css_entries == ('0100_base/css/0000__a.css',)
