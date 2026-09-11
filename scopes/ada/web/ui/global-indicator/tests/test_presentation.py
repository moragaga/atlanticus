from ada.web.ui.display_status import DisplayValue
from ada.web.ui.global_indicator import (
    GlobalIndicatorCollection,
    GlobalIndicatorLastMeasurementState,
    GlobalIndicatorMeasurementState,
    GlobalIndicatorState,
    build_global_indicator,
    build_global_indicators,
)


def _props(component):
    return component.to_plotly_json()['props']


def _walk(component):
    yield component
    children = getattr(component, 'children', None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, 'to_plotly_json'):
            yield from _walk(child)


def _measurement(
    key,
    label,
    actual,
    plan,
    color_class=None,
    actual_kpi_key=None,
    plan_kpi_key=None,
):
    return GlobalIndicatorMeasurementState(
        key=key,
        label=label,
        actual_value=actual,
        plan_value=plan,
        actual_kpi_key=actual_kpi_key,
        plan_kpi_key=plan_kpi_key,
        color_class=color_class,
    )


def test_degraded_values_delegate_icons_to_shared_display_status() -> None:
    state = GlobalIndicatorState(
        key='recuperacion_cu',
        label='Recuperación Cu',
        unit='%',
        measurements=(
            _measurement('dia', 'Día', DisplayValue.invalid(), DisplayValue.not_mapped()),
            _measurement('semana', 'Semana', DisplayValue.empty(), DisplayValue.error()),
        ),
    )

    component = build_global_indicator(state=state)
    images = [item for item in _walk(component) if item.__class__.__name__ == 'Img']
    sources = [_props(item)['src'] for item in images]

    assert len(images) == 4
    assert all('ada_display_status' in source for source in sources)
    assert any(source.endswith('/invalid-data.svg') for source in sources)
    assert any(source.endswith('/not-mapped.svg') for source in sources)
    assert any(source.endswith('/empty-data.svg') for source in sources)
    assert any(source.endswith('/internal-error.svg') for source in sources)


def test_two_measurements_render_only_real_rows_and_omit_optional_last_measurement() -> None:
    state = GlobalIndicatorState(
        key='transportado',
        label='Transportado',
        unit='kt',
        measurements=(
            _measurement('turno', 'Turno', '198', '220'),
            _measurement('dia', 'Día', '201', '220'),
        ),
    )

    component = build_global_indicator(state=state)
    rows = [item for item in _walk(component) if item.__class__.__name__ == 'Tr']
    last_slots = [
        item
        for item in _walk(component)
        if _props(item).get('data-ada-slot') == 'last-measurement'
    ]

    assert _props(component)['data-ada-component-key'] == 'global-indicator'
    assert _props(component)['data-measurement-count'] == '2'
    assert len(rows) == 2
    assert last_slots == []


def test_ok_values_keep_safe_color_classes_and_last_measurement_below_table() -> None:
    state = GlobalIndicatorState(
        key='transportado',
        label='Transportado',
        unit='kt',
        measurements=(
            _measurement('turno', 'Turno', '198', '220', 'text-success fw-bold'),
            _measurement('dia', 'Día', '201', '220'),
        ),
        last_measurement=GlobalIndicatorLastMeasurementState(
            '198',
            color_class='text-success',
        ),
    )

    component = build_global_indicator(state=state)
    values = [
        _props(item).get('className', '')
        for item in _walk(component)
        if item.__class__.__name__ == 'P'
    ]
    content = next(
        item for item in _walk(component) if _props(item).get('data-ada-slot') == 'content'
    )
    table, last_measurement = content.children
    label, actual_value = last_measurement.children

    assert any('text-success fw-bold' in value for value in values)
    assert table.__class__.__name__ == 'Table'
    assert _props(last_measurement)['data-ada-slot'] == 'last-measurement'
    assert label.children == ['Última medición']
    assert actual_value.children == ['198']


def test_collection_renders_exactly_the_indicators_received() -> None:
    for count in (1, 2, 4):
        indicators = tuple(
            GlobalIndicatorState(
                key=f'kpi_{index}',
                label=f'KPI {index}',
                unit='%',
                measurements=(
                    _measurement('dia', 'Día', '88', '90'),
                    _measurement('semana', 'Semana', '89', '90'),
                ),
            )
            for index in range(1, count + 1)
        )

        component = build_global_indicators(collection=GlobalIndicatorCollection(indicators))

        assert _props(component)['data-ada-component-key'] == 'global-indicators'
        assert len(component.children) == count
        assert [_props(child)['data-indicator-key'] for child in component.children] == [
            indicator.key for indicator in indicators
        ]


def test_indicator_uses_table_measurements_and_protects_long_heading_text() -> None:
    state = GlobalIndicatorState(
        key='produccion',
        label='Producción Planta Concentradora Línea Primaria con nombre extenso',
        unit='kt',
        measurements=(
            _measurement('turno', 'Turno', '198', '220'),
            _measurement('dia', 'Día', '201', '220'),
        ),
    )

    component = build_global_indicator(state=state)
    tables = [item for item in _walk(component) if item.__class__.__name__ == 'Table']
    titled = [item for item in _walk(component) if _props(item).get('title') == state.label]

    assert len(tables) == 1
    assert len(titled) == 1


def test_indicator_is_not_inspectable_without_value_kpi_keys() -> None:
    state = GlobalIndicatorState(
        key='transportado',
        label='Transportado',
        unit='kt',
        measurements=(
            _measurement('turno', 'Turno', '198', '220'),
            _measurement('dia', 'Día', '201', '220'),
        ),
    )

    component = build_global_indicator(state=state)

    assert all('data-kpi-inspection-key' not in _props(item) for item in _walk(component))
    assert 'data-definition-key' not in _props(component)


def test_each_value_can_opt_into_its_own_kpi_definition() -> None:
    state = GlobalIndicatorState(
        key='transportado_card',
        label='Transportado',
        unit='kt',
        measurements=(
            _measurement(
                'turno',
                'Turno',
                '198',
                '220',
                actual_kpi_key='transported.shift.actual',
                plan_kpi_key='transported.shift.plan',
            ),
            _measurement(
                'dia',
                'Día',
                '201',
                '220',
                actual_kpi_key='transported.day.actual',
                plan_kpi_key='transported.day.plan',
            ),
        ),
        last_measurement=GlobalIndicatorLastMeasurementState(
            '202',
            actual_kpi_key='transported.latest',
        ),
    )

    component = build_global_indicator(state=state)
    root_props = _props(component)
    triggers = [item for item in _walk(component) if _props(item).get('data-kpi-inspection-key')]
    keys = [_props(item)['data-kpi-inspection-key'] for item in triggers]

    assert root_props['data-indicator-key'] == 'transportado_card'
    assert 'data-kpi-inspection-key' not in root_props
    assert keys == [
        'transported.shift.actual',
        'transported.shift.plan',
        'transported.day.actual',
        'transported.day.plan',
        'transported.latest',
    ]
    assert all('role' not in _props(item) for item in triggers)
    assert all('tabIndex' not in _props(item) for item in triggers)
    assert all('aria-haspopup' not in _props(item) for item in triggers)

    measurement_labels = [
        item for item in _walk(component) if item.__class__.__name__ == 'Th'
    ]
    assert all('data-kpi-inspection-key' not in _props(item.children[0]) for item in measurement_labels)


def test_value_without_kpi_key_remains_neutral_inside_inspectable_row() -> None:
    state = GlobalIndicatorState(
        key='transportado_card',
        label='Transportado',
        unit='kt',
        measurements=(
            _measurement(
                'turno',
                'Turno',
                '198',
                '220',
                actual_kpi_key='transported.shift.actual',
            ),
            _measurement('dia', 'Día', '201', '220'),
        ),
    )

    component = build_global_indicator(state=state)
    triggers = [item for item in _walk(component) if _props(item).get('data-kpi-inspection-key')]

    assert len(triggers) == 1
    assert _props(triggers[0])['data-kpi-inspection-key'] == 'transported.shift.actual'
