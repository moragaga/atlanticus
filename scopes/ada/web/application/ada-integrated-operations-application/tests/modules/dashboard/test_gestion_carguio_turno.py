from __future__ import annotations

from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.gestion_carguio_turno import (
    GESTION_CARGUIO_TURNO_KPI_KEY,
    build_gestion_carguio_turno,
    map_gestion_carguio_turno_store,
)
from ada.web.ui.display_status import DisplayStatus


def _json(value: object) -> dict[str, object]:
    return {'status': 'ok', 'value_kind': 'json', 'value': value}


def _store(value: object) -> dict[str, object]:
    return {
        'latest': {
            'values': {
                GESTION_CARGUIO_TURNO_KPI_KEY: _json(value),
            }
        }
    }


def _row(equipo: str, fase: str) -> dict[str, object]:
    return {
        'equipo': equipo,
        'fase': fase,
        'uebd_pct': '72',
        'disponibilidad_fisica_pct': '85',
        'rendimiento_efectivo_tph': '2450',
        'cola_pala_min': '4.2',
        'estado': 'E',
        'razon': '-',
    }


def _props(component):
    return component.to_plotly_json()['props']


def _walk(component):
    yield component
    children = _props(component).get('children')
    if hasattr(children, 'to_plotly_json'):
        yield from _walk(children)
    elif isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, 'to_plotly_json'):
                yield from _walk(child)


def test_gestion_carguio_turno_preserves_section_and_row_order() -> None:
    state, status = map_gestion_carguio_turno_store(
        _store(
            {
                'data_state': 'ok',
                'sections': [
                    {
                        'label': 'PALAS',
                        'rows': [
                            _row('PH01', 'F9'),
                            _row('PH02', 'F10'),
                        ],
                    },
                    {
                        'label': 'OTRA CATEGORÍA',
                        'rows': [
                            _row('PC01', 'F11'),
                        ],
                    },
                ],
            }
        )
    )

    assert status is DisplayStatus.OK
    assert state is not None
    assert [section.label for section in state.sections] == [
        'PALAS',
        'OTRA CATEGORÍA',
    ]
    assert [row.equipo for row in state.sections[0].rows] == ['PH01', 'PH02']
    assert state.sections[0].rows[0].rendimiento_efectivo_tph == '2450'


def test_gestion_carguio_turno_supports_unshift_without_sections() -> None:
    state, status = map_gestion_carguio_turno_store(
        _store({'data_state': 'unshift', 'sections': []})
    )

    assert status is DisplayStatus.OK
    assert state is not None
    assert state.sections == ()


def test_gestion_carguio_turno_rejects_legacy_flat_rows_contract() -> None:
    state, status = map_gestion_carguio_turno_store(
        _store(
            {
                'data_state': 'ok',
                'rows': [
                    _row('PH01', 'F9'),
                ],
            }
        )
    )

    assert state is None
    assert status is DisplayStatus.INVALID


def test_gestion_carguio_turno_inspects_complete_json_surface() -> None:
    state, status = map_gestion_carguio_turno_store(
        _store({'data_state': 'unshift', 'sections': []})
    )
    component = build_gestion_carguio_turno(state, status)
    inspection_nodes = [
        node for node in _walk(component) if _props(node).get('data-kpi-inspection-key') is not None
    ]

    assert len(inspection_nodes) == 1
    assert _props(inspection_nodes[0])['data-kpi-inspection-key'] == GESTION_CARGUIO_TURNO_KPI_KEY
