from importlib.resources import files


def test_mobile_definition_rows_hide_placeholders_with_specific_selector() -> None:
    css = (
        files('ada.web.kpis.definition.web')
        .joinpath('resources/css/10-kpi-definition-editor.css')
        .read_text(encoding='utf-8')
    )
    mobile = css.split('@media (max-width: 48rem)', maxsplit=1)[1]

    assert (
        '.ada-kpi-definition__table '
        'tr.ada-kpi-definition__row--placeholder'
    ) in mobile
    assert 'box-sizing: border-box;' in mobile
