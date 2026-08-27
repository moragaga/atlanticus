from ada.web.inspection.surface import build_kpi_inspection_surface_fragment


def test_surface_markup_is_accessible_and_starts_inert() -> None:
    markup = build_kpi_inspection_surface_fragment()

    assert 'aria-hidden="true" inert' in markup
    assert 'role="dialog"' in markup
    assert 'aria-modal="true"' in markup
    assert 'aria-live="polite"' in markup
    assert 'data-kpi-inspection-close' in markup


def test_surface_markup_declares_all_controller_states() -> None:
    markup = build_kpi_inspection_surface_fragment()

    for state in ('loading', 'ready', 'unavailable', 'error'):
        assert f'data-kpi-inspection-view="{state}"' in markup
    assert 'data-kpi-inspection-fields' in markup
    assert 'data-kpi-inspection-empty' in markup
