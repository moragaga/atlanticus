from pathlib import Path

import pytest

from atlanticus.web.assets import AssetLayer, publish_asset_layers
from atlanticus.web.errors import WebAssetError, WebDefinitionError


def _manifest_layer(
    tmp_path: Path,
    name: str,
    order: int,
    *,
    css: dict[str, str],
    js: dict[str, str],
):
    root = tmp_path / name / 'resources'
    (root / 'css').mkdir(parents=True)
    (root / 'js').mkdir(parents=True)
    for filename, content in css.items():
        (root / 'css' / filename).write_text(content, encoding='utf-8')
    for filename, content in js.items():
        (root / 'js' / filename).write_text(content, encoding='utf-8')
    (root / 'css' / 'css.list').write_text('\n'.join(css) + '\n', encoding='utf-8')
    (root / 'js' / 'js.list').write_text('\n'.join(js) + '\n', encoding='utf-8')
    return AssetLayer(name=name, load_order=order, source_directory=tmp_path / name)


def test_optimized_publication_bundles_css_in_layer_and_manifest_order(tmp_path):
    wheel = _manifest_layer(
        tmp_path,
        'wheel',
        100,
        css={
            '20-wheel.css': '.wheel-second { color: blue; }',
            '10-wheel.css': '.wheel-first { color: red; }',
        },
        js={},
    )
    local_root = tmp_path / 'local' / 'resources'
    (local_root / 'css').mkdir(parents=True)
    (local_root / 'js').mkdir(parents=True)
    (local_root / 'css' / '20-local.css').write_text('.local-second { color: black; }')
    (local_root / 'css' / '10-local.css').write_text('.local-first { color: white; }')
    local = AssetLayer(
        name='local',
        load_order=900,
        source_directory=tmp_path / 'local',
        filename_ordered=True,
    )

    publication = publish_asset_layers(
        layers=(local, wheel),
        publications_root=tmp_path / 'published',
        optimize=True,
    )

    assert publication.css_entries == ('app.min.css',)
    css = (publication.assets_root / 'app.min.css').read_text(encoding='utf-8')
    assert css.index('.wheel-second') < css.index('.wheel-first')
    assert css.index('.wheel-first') < css.index('.local-first')
    assert css.index('.local-first') < css.index('.local-second')
    assert ' { ' not in css


def test_optimized_publication_minifies_javascript_without_concatenating(tmp_path):
    layer = _manifest_layer(
        tmp_path,
        'wheel',
        100,
        css={},
        js={
            '10-first.js': 'const first = () => { return `first ${1}`; };\n',
            '20-second.js': "const second = () => { return 'second'; };\n",
        },
    )

    publication = publish_asset_layers(
        layers=(layer,),
        publications_root=tmp_path / 'published',
        optimize=True,
    )

    assert publication.js_entries == (
        '0100_wheel/js/0000__10-first.js',
        '0100_wheel/js/0001__20-second.js',
    )
    first = (publication.assets_root / publication.js_entries[0]).read_text(encoding='utf-8')
    second = (publication.assets_root / publication.js_entries[1]).read_text(encoding='utf-8')
    assert 'const first=' in first
    assert '`first ${1}`' in first
    assert 'const second=' in second
    assert '\n\n' not in first


def test_optimized_javascript_preserves_wheel_then_local_order(tmp_path):
    wheel = _manifest_layer(
        tmp_path,
        'wheel',
        100,
        css={},
        js={'20-wheel.js': 'const wheel = 20;'},
    )
    local_root = tmp_path / 'local' / 'resources'
    (local_root / 'css').mkdir(parents=True)
    (local_root / 'js').mkdir(parents=True)
    (local_root / 'js' / '20-local.js').write_text('const localSecond = 20;', encoding='utf-8')
    (local_root / 'js' / '10-local.js').write_text('const localFirst = 10;', encoding='utf-8')
    local = AssetLayer(
        name='local',
        load_order=900,
        source_directory=tmp_path / 'local',
        filename_ordered=True,
    )

    publication = publish_asset_layers(
        layers=(local, wheel),
        publications_root=tmp_path / 'published',
        optimize=True,
    )

    assert publication.js_entries == (
        '0100_wheel/js/0000__20-wheel.js',
        '0900_local/js/0000__10-local.js',
        '0900_local/js/0001__20-local.js',
    )


def test_optimized_and_unoptimized_publications_have_distinct_revisions(tmp_path):
    layer = _manifest_layer(
        tmp_path,
        'wheel',
        100,
        css={'10-a.css': '.a { color: red; }'},
        js={'10-a.js': 'const value = 1;'},
    )

    regular = publish_asset_layers(layers=(layer,), publications_root=tmp_path / 'published')
    optimized = publish_asset_layers(
        layers=(layer,),
        publications_root=tmp_path / 'published',
        optimize=True,
    )

    assert regular.revision != optimized.revision
    assert len(regular.css_entries) == 1
    assert optimized.css_entries == ('app.min.css',)


def test_filename_ordered_local_layer_requires_numeric_prefix(tmp_path):
    root = tmp_path / 'local' / 'resources'
    (root / 'css').mkdir(parents=True)
    (root / 'js').mkdir(parents=True)
    (root / 'css' / 'override.css').write_text('.override {}', encoding='utf-8')
    layer = AssetLayer(
        name='local',
        load_order=900,
        source_directory=tmp_path / 'local',
        filename_ordered=True,
    )

    with pytest.raises(WebAssetError, match='must be a root file with a numeric prefix'):
        publish_asset_layers(layers=(layer,), publications_root=tmp_path / 'published')


def test_packaged_layer_cannot_use_filename_ordering():
    with pytest.raises(WebDefinitionError, match='must use css.list/js.list ordering'):
        AssetLayer(name='package', load_order=100, package='example', filename_ordered=True)


def test_filename_ordered_application_layer_must_follow_packaged_layers(tmp_path):
    packaged = AssetLayer(name='package', load_order=900, package='example')
    local = AssetLayer(
        name='local',
        load_order=800,
        source_directory=tmp_path / 'local',
        filename_ordered=True,
    )

    with pytest.raises(WebDefinitionError, match='must load after packaged assets'):
        publish_asset_layers(
            layers=(packaged, local),
            publications_root=tmp_path / 'published',
        )


def test_filename_ordered_local_layer_rejects_list_files(tmp_path):
    root = tmp_path / 'local' / 'resources'
    (root / 'css').mkdir(parents=True)
    (root / 'js').mkdir(parents=True)
    (root / 'css' / '10-override.css').write_text('.override {}', encoding='utf-8')
    (root / 'css' / 'css.list').write_text('10-override.css\n', encoding='utf-8')
    layer = AssetLayer(
        name='local',
        load_order=900,
        source_directory=tmp_path / 'local',
        filename_ordered=True,
    )

    with pytest.raises(WebAssetError, match='must not define a list file'):
        publish_asset_layers(layers=(layer,), publications_root=tmp_path / 'published')


def test_filename_ordered_local_layer_rejects_nested_assets(tmp_path):
    root = tmp_path / 'local' / 'resources'
    (root / 'css' / 'nested').mkdir(parents=True)
    (root / 'js').mkdir(parents=True)
    (root / 'css' / 'nested' / '10-override.css').write_text(
        '.override {}',
        encoding='utf-8',
    )
    layer = AssetLayer(
        name='local',
        load_order=900,
        source_directory=tmp_path / 'local',
        filename_ordered=True,
    )

    with pytest.raises(WebAssetError, match='must be a root file with a numeric prefix'):
        publish_asset_layers(layers=(layer,), publications_root=tmp_path / 'published')
