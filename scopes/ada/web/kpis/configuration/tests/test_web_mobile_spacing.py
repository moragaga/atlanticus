from importlib.resources import files


def test_mobile_kpi_rows_keep_symmetric_outer_spacing() -> None:
    css = (
        files('ada.web.kpis.configuration.web')
        .joinpath('resources/css/10-kpi-configuration-editor.css')
        .read_text(encoding='utf-8')
    )

    mobile = css.split('@media (max-width: 48rem)', maxsplit=1)[1]
    row = mobile.split('.ada-kpi-configuration__row {', maxsplit=1)[1]
    row = row.split('}', maxsplit=1)[0]

    assert 'width: 100%;' in row
    assert 'max-width: 100%;' in row
    assert 'box-sizing: border-box;' in row
    assert 'padding: .35rem .7rem;' in row


def test_mobile_placeholder_rows_override_generic_table_row_display() -> None:
    css = (
        files('ada.web.kpis.configuration.web')
        .joinpath('resources/css/10-kpi-configuration-editor.css')
        .read_text(encoding='utf-8')
    )

    mobile = css.split('@media (max-width: 48rem)', maxsplit=1)[1]

    assert (
        '.ada-kpi-configuration__table '
        'tr.ada-kpi-configuration__row--placeholder'
    ) in mobile
    assert (
        '.ada-kpi-configuration__table '
        'tr.ada-kpi-configuration__row--empty'
    ) in mobile

    hidden_block = mobile.split(
        '.ada-kpi-configuration__table '
        'tr.ada-kpi-configuration__row--placeholder',
        maxsplit=1,
    )[1]
    hidden_block = hidden_block.split('}', maxsplit=1)[0]

    assert 'display: none;' in hidden_block
