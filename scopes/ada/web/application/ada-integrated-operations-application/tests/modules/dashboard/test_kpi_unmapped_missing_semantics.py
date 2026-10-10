from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.decoder import (
    decode_carguio_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.carguio_global_turno import (
    CARGUIO_GLOBAL_TURNO_KPI_KEY,
    map_carguio_global_turno_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.equipos_servicio import (
    EQUIPOS_SERVICIO_KPI_KEY,
    map_equipos_servicio_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.gestion_carguio_turno import (
    GESTION_CARGUIO_TURNO_KPI_KEY,
    map_gestion_carguio_turno_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.decoder import (
    decode_general_mina_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.movimiento_mina import (
    MOVIMIENTO_MINA_KPI_KEY,
    MovimientoMinaUnavailableError,
    map_movimiento_mina_readings,
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
from ada.web.kpis.collector import KpiLatestValueState
from ada.web.ui.display_status import DisplayStatus


def _missing_entry() -> dict[str, object]:
    return {
        'status': 'missing',
        'value_kind': None,
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def test_empty_component_latest_means_not_mapped() -> None:
    empty_store = {'latest': None}
    readings = decode_general_mina_store(empty_store)
    remanentes = map_remanentes_readings(readings)
    perforacion = map_perforacion_readings(readings)
    mp10 = map_mp10_readings(readings)

    carguio_readings = decode_carguio_store(empty_store)
    global_state, global_status = map_carguio_global_turno_readings(carguio_readings)
    equipos_state, equipos_status = map_equipos_servicio_readings(carguio_readings)
    gestion_state, gestion_status = map_gestion_carguio_turno_readings(carguio_readings)

    assert remanentes.summary_status is DisplayStatus.NOT_MAPPED
    assert remanentes.stock_3080.value.status is DisplayStatus.NOT_MAPPED
    assert perforacion.resumen_status is DisplayStatus.NOT_MAPPED
    assert perforacion.detalle_status is DisplayStatus.NOT_MAPPED
    assert mp10.instant_status is DisplayStatus.NOT_MAPPED
    assert mp10.projection_status is DisplayStatus.NOT_MAPPED
    assert global_state is None
    assert equipos_state is None
    assert gestion_state is None
    assert global_status is DisplayStatus.NOT_MAPPED
    assert equipos_status is DisplayStatus.NOT_MAPPED
    assert gestion_status is DisplayStatus.NOT_MAPPED
    with pytest.raises(MovimientoMinaUnavailableError) as error:
        map_movimiento_mina_readings(readings)
    assert error.value.state is KpiLatestValueState.NOT_MAPPED


def test_explicit_missing_kpi_means_empty() -> None:
    store = _store(
        {
            MOVIMIENTO_MINA_KPI_KEY: _missing_entry(),
            REMANENTES_SUMMARY_KPI_KEY: _missing_entry(),
            STOCK_3080_KPI_KEY: _missing_entry(),
            PERFORACION_RESUMEN_KPI_KEY: _missing_entry(),
            PERFORACION_DETALLE_KPI_KEY: _missing_entry(),
            MP10_HOTEL_MINA_INST_KPI_KEY: _missing_entry(),
            MP10_HOTEL_MINA_PROY_KPI_KEY: _missing_entry(),
            CARGUIO_GLOBAL_TURNO_KPI_KEY: _missing_entry(),
            EQUIPOS_SERVICIO_KPI_KEY: _missing_entry(),
            GESTION_CARGUIO_TURNO_KPI_KEY: _missing_entry(),
        }
    )
    readings = decode_general_mina_store(store)
    remanentes = map_remanentes_readings(readings)
    perforacion = map_perforacion_readings(readings)
    mp10 = map_mp10_readings(readings)

    carguio_readings = decode_carguio_store(store)
    global_state, global_status = map_carguio_global_turno_readings(carguio_readings)
    equipos_state, equipos_status = map_equipos_servicio_readings(carguio_readings)
    gestion_state, gestion_status = map_gestion_carguio_turno_readings(carguio_readings)

    assert remanentes.summary_status is DisplayStatus.EMPTY
    assert remanentes.stock_3080.value.status is DisplayStatus.EMPTY
    assert perforacion.resumen_status is DisplayStatus.EMPTY
    assert perforacion.detalle_status is DisplayStatus.EMPTY
    assert mp10.instant_status is DisplayStatus.EMPTY
    assert mp10.projection_status is DisplayStatus.EMPTY
    assert global_state is None
    assert equipos_state is None
    assert gestion_state is None
    assert global_status is DisplayStatus.EMPTY
    assert equipos_status is DisplayStatus.EMPTY
    assert gestion_status is DisplayStatus.EMPTY
    with pytest.raises(MovimientoMinaUnavailableError) as error:
        map_movimiento_mina_readings(readings)
    assert error.value.state is KpiLatestValueState.MISSING
