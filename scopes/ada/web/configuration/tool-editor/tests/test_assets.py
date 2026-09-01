from importlib.resources import files


def test_css_manifest_contains_complete_editor_stylesheets() -> None:
    package_root = files('ada.web.configuration.tool_editor')
    css_root = package_root.joinpath('resources/css')
    manifest = css_root.joinpath('css.list').read_text(encoding='utf-8')
    source_stylesheet = css_root.joinpath('tool-editor.css').read_text(encoding='utf-8')
    structure_stylesheet = css_root.joinpath('structure-editor.css').read_text(encoding='utf-8')

    assert tuple(manifest.splitlines()) == (
        'tool-editor.css',
        'structure-editor.css',
    )
    assert '.ada-tool-source-editor' in source_stylesheet
    assert '.ada-tool-structure-editor' in structure_stylesheet
