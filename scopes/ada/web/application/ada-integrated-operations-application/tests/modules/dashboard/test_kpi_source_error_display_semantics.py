from __future__ import annotations

from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.carguio_global_turno import (
    CARGUIO_GLOBAL_TURNO_KPI_KEY,
    map_carguio_global_turno_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.equipos_servicio import (
    EQUIPOS_SERVICIO_KPI_KEY,
    map_equipos_servicio_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.gestion_carguio_turno import (
    GESTION_CARGUIO_TURNO_KPI_KEY,
    map_gestion_carguio_turno_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.decoder import (
    decode_general_mina_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.mp10 import (
    MP10_HOTEL_MINA_INST_KPI_KEY,
    MP10_HOTEL_MINA_PROY_KPI_KEY,
    map_mp10_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.perforacion import (
    PERFORACION_DETALLE_KPI_KEY,
    PERFORACION_RESUMEN_KPI_KEY,
    map_perforacion_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.remanentes import (
    REMANENTES_SUMMARY_KPI_KEY,
    STOCK_3080_KPI_KEY,
    map_remanentes_readings,
)
from ada.web.ui.display_status import DisplayStatus


def _entry(*, value_kind: str) -> dict[str, object]:
    return {
        'status': 'error',
        'value_kind': value_kind,
        'value': None,
        'value_type': ('text' if value_kind == 'value' else None),
        'parsed_value': None,
    }


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def test_carguio_source_errors_are_invalid_data() -> None:
    store = _store(
        {
            CARGUIO_GLOBAL_TURNO_KPI_KEY: _entry(value_kind='json'),
            EQUIPOS_SERVICIO_KPI_KEY: _entry(value_kind='json'),
            GESTION_CARGUIO_TURNO_KPI_KEY: _entry(value_kind='json'),
        }
    )

    global_state, global_status = map_carguio_global_turno_store(store)
    equipos_state, equipos_status = map_equipos_servicio_store(store)
    gestion_state, gestion_status = map_gestion_carguio_turno_store(store)

    assert global_state is None
    assert equipos_state is None
    assert gestion_state is None
    assert global_status is DisplayStatus.INVALID
    assert equipos_status is DisplayStatus.INVALID
    assert gestion_status is DisplayStatus.INVALID


def test_general_mina_source_errors_are_invalid_data() -> None:
    remanentes = map_remanentes_readings(
        decode_general_mina_store(_store({
            REMANENTES_SUMMARY_KPI_KEY: _entry(value_kind='json'),
            STOCK_3080_KPI_KEY: _entry(value_kind='value'),
        }))
    )
    perforacion = map_perforacion_readings(
        decode_general_mina_store(_store({
            PERFORACION_RESUMEN_KPI_KEY: _entry(value_kind='json'),
            PERFORACION_DETALLE_KPI_KEY: _entry(value_kind='json'),
        }))
    )
    mp10 = map_mp10_readings(
        decode_general_mina_store(_store({
            MP10_HOTEL_MINA_INST_KPI_KEY: _entry(value_kind='json'),
            MP10_HOTEL_MINA_PROY_KPI_KEY: _entry(value_kind='json'),
        }))
    )

    assert remanentes.summary is None
    assert remanentes.summary_status is DisplayStatus.INVALID
    assert remanentes.stock_3080.value.status is DisplayStatus.INVALID
    assert perforacion.resumen is None
    assert perforacion.detalle is None
    assert perforacion.resumen_status is DisplayStatus.INVALID
    assert perforacion.detalle_status is DisplayStatus.INVALID
    assert mp10.instant is None
    assert mp10.projection is None
    assert mp10.instant_status is DisplayStatus.INVALID
    assert mp10.projection_status is DisplayStatus.INVALID
