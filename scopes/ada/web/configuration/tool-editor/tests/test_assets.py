from importlib.resources import files


def test_css_manifest_contains_editor_stylesheet() -> None:
    package_root = files('ada.web.configuration.tool_editor')
    manifest = package_root.joinpath('resources/css/css.list').read_text(encoding='utf-8')
    stylesheet = package_root.joinpath('resources/css/tool-editor.css').read_text(encoding='utf-8')

    assert manifest.strip() == 'tool-editor.css'
    assert '.ada-tool-source-editor' in stylesheet
