from importlib.resources import files


def test_dashboard_presentation_javascript_is_packaged() -> None:
    resources = files(
        'ada.web.application.integrated_operations.modules.dashboard'
    ).joinpath('resources/js')

    assert resources.joinpath('js.list').read_text(encoding='utf-8').splitlines() == [
        '10_presentation.js'
    ]
    assert resources.joinpath('10_presentation.js').is_file()
