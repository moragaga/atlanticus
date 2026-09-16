from importlib.resources import files


def test_css_manifest_lists_editor_stylesheets() -> None:
    css_root = files('ada.web.tools.configuration.web').joinpath('resources/css')
    manifest = css_root.joinpath('css.list').read_text(encoding='utf-8')

    assert tuple(manifest.splitlines()) == (
        'tool-editor.css',
        'structure-editor.css',
    )

